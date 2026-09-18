-- autopilot.lua — Rotador autónomo dentro de OBS
--
-- Parte del OBS Automation Manager (rama v1.8.x). Se instala UNA VEZ en
-- el OBS del servidor, mediante Tools -> Scripts -> +. Después de eso,
-- la app cliente (la que corre en la laptop del operador) se comunica
-- con este script vía WebSocket usando dos "text sources" ocultos que
-- funcionan como buzones de datos:
--
--   __autopilot_config__  — la app escribe JSON con la playlist.
--   __autopilot_state__   — este script publica JSON con su estado.
--
-- El script alterna entre dos modos:
--
--   standby  — la app está conectada y controlando la rotación. El
--              script sólo publica estado y espera. Se activa cuando
--              recibe heartbeats frescos de la app (últimos 30s).
--   active   — la app se cerró o crashó (heartbeat viejo). El script
--              toma control y rota escenas por su cuenta según la
--              playlist recibida (respetando programación horaria).
--
-- El hand-off es transparente: cuando la app se cierra, publica un
-- último config con el índice activo + segundos restantes, y el script
-- retoma exactamente desde ahí.
--
-- Protocolo JSON detallado: obs_scripts/PROTOCOL.md

local obs = obslua

-- ==========================================================================
-- Constantes
-- ==========================================================================

local SCRIPT_VERSION = "1.0.0"
local CONFIG_SOURCE = "__autopilot_config__"
local STATE_SOURCE = "__autopilot_state__"

-- Cadencia de los timers internos
local TICK_ROTATION_MS = 1000     -- 1s: countdown + rotación + publish state
local TICK_CONFIG_MS = 500        -- 500ms: chequeo de config nueva

-- Sin heartbeat de la app por más de N segundos → el script toma control
local HEARTBEAT_TIMEOUT_SEC = 30

-- Cuando ningún item de la playlist está en su ventana horaria, esperar
-- este intervalo antes de volver a chequear.
local RETRY_WHEN_NO_ACTIVE_SEC = 60

-- ==========================================================================
-- Estado interno
-- ==========================================================================

local playlist = {}                -- lista de {name, duration_seg, active_days, active_time_start, active_time_end}
local active_index = 0             -- 0 = ninguno; 1-indexed en Lua
local seconds_remaining = 0
local last_rotation_at = ""
local last_config_version = 0
local last_heartbeat_epoch = 0     -- os.time() del último heartbeat de la app
local mode = "standby"             -- "standby" | "active"

-- ==========================================================================
-- Utilidades
-- ==========================================================================

local function log_info(msg)
    obs.script_log(obs.LOG_INFO, "[autopilot] " .. msg)
end

local function log_warn(msg)
    obs.script_log(obs.LOG_WARNING, "[autopilot] " .. msg)
end

local function now_iso()
    return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

-- Test si el bit N-esimo (0-indexed) está seteado en value.
-- Compatible con Lua 5.1 (sin operadores bitwise nativos).
local function has_bit(value, bit_index)
    return math.floor(value / (2 ^ bit_index)) % 2 == 1
end

-- "HH:MM" → minutos desde 0h. Devuelve nil si no parsea.
local function hhmm_to_min(s)
    if s == nil or s == "" then return nil end
    local h, m = string.match(s, "^(%d+):(%d+)$")
    if h == nil then return nil end
    h, m = tonumber(h), tonumber(m)
    if h == nil or m == nil then return nil end
    return h * 60 + m
end

-- Devuelve true si la escena está dentro de su ventana horaria configurada.
-- Mismo criterio que views/schedule_widget.is_scene_active_now en la app:
-- bitmask days (bit 0 = lunes, ..., bit 6 = domingo) + rango HH:MM opcional
-- que puede cruzar la medianoche (22:00 → 02:00).
local function is_in_window(active_days, time_start, time_end)
    active_days = active_days or 127
    if active_days == 0 then active_days = 127 end
    local now = os.date("*t")
    -- Lua os.date wday: 1=domingo..7=sábado. Convertir a bit 0=lunes..6=domingo.
    local wday_bit = (now.wday - 2) % 7
    if not has_bit(active_days, wday_bit) then
        return false
    end
    local start_min = hhmm_to_min(time_start)
    local end_min = hhmm_to_min(time_end)
    if start_min == nil or end_min == nil then
        return true  -- sin ventana horaria → siempre activa (con día ok)
    end
    local now_min = now.hour * 60 + now.min
    if start_min <= end_min then
        return now_min >= start_min and now_min < end_min
    else
        -- Ventana cruza medianoche
        return now_min >= start_min or now_min < end_min
    end
end

-- ==========================================================================
-- Lectura / escritura de text sources (los "buzones" con la app)
-- ==========================================================================

-- Lee el texto del text source `name`. Devuelve "" si no existe todavía.
local function read_text_source(name)
    local source = obs.obs_get_source_by_name(name)
    if source == nil then return "" end
    local settings = obs.obs_source_get_settings(source)
    local text = obs.obs_data_get_string(settings, "text") or ""
    obs.obs_data_release(settings)
    obs.obs_source_release(source)
    return text
end

-- Escribe `text` en el text source `name`. Si el source no existe, lo crea.
-- El source queda "suelto" (no en ninguna scene) — solo sirve como buzón.
local function write_text_source(name, text)
    local source = obs.obs_get_source_by_name(name)
    if source == nil then
        -- Crear el text source. Preferir text_gdiplus_v3 (OBS 30+);
        -- fallback a v2 en versiones anteriores.
        local settings = obs.obs_data_create()
        obs.obs_data_set_string(settings, "text", text or "")
        source = obs.obs_source_create("text_gdiplus_v3", name, settings, nil)
        obs.obs_data_release(settings)
        if source == nil then
            settings = obs.obs_data_create()
            obs.obs_data_set_string(settings, "text", text or "")
            source = obs.obs_source_create("text_gdiplus_v2", name, settings, nil)
            obs.obs_data_release(settings)
        end
        if source == nil then
            log_warn("no se pudo crear text source: " .. name)
            return
        end
        log_info("creado text source: " .. name)
    else
        local settings = obs.obs_data_create()
        obs.obs_data_set_string(settings, "text", text or "")
        obs.obs_source_update(source, settings)
        obs.obs_data_release(settings)
    end
    obs.obs_source_release(source)
end

-- ==========================================================================
-- Rotación
-- ==========================================================================

-- Activa `scene_name` como escena de Program en OBS.
local function activate_scene(scene_name)
    local source = obs.obs_get_source_by_name(scene_name)
    if source == nil then
        log_warn("escena no existe en OBS: " .. scene_name)
        return false
    end
    obs.obs_frontend_set_current_scene(source)
    obs.obs_source_release(source)
    return true
end

-- Devuelve el índice (1-indexed) del próximo item que esté en su ventana
-- horaria, empezando por (active_index + 1) y dando la vuelta. Devuelve
-- nil si nada está activo ahora.
local function pick_next_in_window()
    local n = #playlist
    if n == 0 then return nil end
    local start = active_index > 0 and active_index or 0
    for offset = 1, n do
        local candidate = ((start - 1 + offset) % n) + 1
        local entry = playlist[candidate]
        if is_in_window(entry.active_days, entry.active_time_start, entry.active_time_end) then
            return candidate
        end
    end
    return nil
end

-- Rota a la siguiente escena. Si nada está en ventana, agenda retry.
local function rotate()
    local idx = pick_next_in_window()
    if idx == nil then
        active_index = 0
        seconds_remaining = RETRY_WHEN_NO_ACTIVE_SEC
        log_info("nada en ventana horaria; reintenta en " .. RETRY_WHEN_NO_ACTIVE_SEC .. "s")
        return
    end
    active_index = idx
    local entry = playlist[idx]
    seconds_remaining = entry.duration_seg or 20
    if seconds_remaining < 1 then seconds_remaining = 1 end
    if activate_scene(entry.name) then
        last_rotation_at = now_iso()
        log_info("rotate → '" .. entry.name .. "' (" .. seconds_remaining .. "s)")
    end
end

-- ==========================================================================
-- Publicación de estado
-- ==========================================================================

local function publish_state()
    local data = obs.obs_data_create()
    obs.obs_data_set_string(data, "script_version", SCRIPT_VERSION)
    obs.obs_data_set_string(data, "mode", mode)
    local active_name = ""
    if active_index >= 1 and active_index <= #playlist then
        active_name = playlist[active_index].name
    end
    obs.obs_data_set_string(data, "active_scene", active_name)
    obs.obs_data_set_int(data, "active_index", active_index)
    obs.obs_data_set_int(data, "seconds_remaining", seconds_remaining)
    obs.obs_data_set_string(data, "last_rotation_at", last_rotation_at)
    obs.obs_data_set_int(data, "last_config_version", last_config_version)
    obs.obs_data_set_int(data, "playlist_size", #playlist)
    obs.obs_data_set_string(data, "updated_at", now_iso())
    local json = obs.obs_data_get_json(data)
    obs.obs_data_release(data)
    write_text_source(STATE_SOURCE, json)
end

-- ==========================================================================
-- Ingestión de config desde el buzón
-- ==========================================================================

local function ingest_config()
    local text = read_text_source(CONFIG_SOURCE)
    if text == nil or text == "" then return end
    local data = obs.obs_data_create_from_json(text)
    if data == nil then return end

    local version = obs.obs_data_get_int(data, "version")

    -- Heartbeat: cualquier config con timestamp fresco marca a la app como viva
    local heartbeat_str = obs.obs_data_get_string(data, "app_heartbeat_at") or ""
    if heartbeat_str ~= "" then
        last_heartbeat_epoch = os.time()
    end

    -- Solo re-cargar playlist si version subió
    if version <= last_config_version then
        obs.obs_data_release(data)
        return
    end

    -- Extraer playlist
    local playlist_arr = obs.obs_data_get_array(data, "playlist")
    if playlist_arr ~= nil then
        local new_playlist = {}
        local count = obs.obs_data_array_count(playlist_arr)
        for i = 0, count - 1 do
            local item = obs.obs_data_array_item(playlist_arr, i)
            table.insert(new_playlist, {
                name = obs.obs_data_get_string(item, "name") or "",
                duration_seg = obs.obs_data_get_int(item, "duration_seg"),
                active_days = obs.obs_data_get_int(item, "active_days"),
                active_time_start = obs.obs_data_get_string(item, "active_time_start"),
                active_time_end = obs.obs_data_get_string(item, "active_time_end"),
            })
            obs.obs_data_release(item)
        end
        obs.obs_data_array_release(playlist_arr)
        playlist = new_playlist
    end

    -- Handoff explícito (la app publica esto cuando cierra o entrega el control)
    local handoff = obs.obs_data_get_obj(data, "handoff")
    if handoff ~= nil then
        local h_scene = obs.obs_data_get_string(handoff, "active_scene") or ""
        local h_remaining = obs.obs_data_get_int(handoff, "seconds_remaining")
        if h_scene ~= "" then
            for i, entry in ipairs(playlist) do
                if entry.name == h_scene then
                    active_index = i
                    if h_remaining > 0 then
                        seconds_remaining = h_remaining
                    end
                    log_info("handoff recibido: '" .. h_scene ..
                             "' con " .. seconds_remaining .. "s restantes")
                    break
                end
            end
        end
        obs.obs_data_release(handoff)
    end

    last_config_version = version
    obs.obs_data_release(data)
    log_info("config v" .. version .. " cargada (" .. #playlist .. " escenas)")
end

-- ==========================================================================
-- Ticks
-- ==========================================================================

-- Cada 500ms: chequear config nueva
local function tick_config()
    ingest_config()
end

-- Cada 1s: mode transitions + countdown + rotación + state publish
local function tick_rotation()
    -- Determinar modo según edad del último heartbeat
    if last_heartbeat_epoch > 0 and
       (os.time() - last_heartbeat_epoch) < HEARTBEAT_TIMEOUT_SEC then
        mode = "standby"
    else
        mode = "active"
    end

    if mode == "active" then
        if seconds_remaining > 0 then
            seconds_remaining = seconds_remaining - 1
            if seconds_remaining == 0 then
                rotate()
            end
        elseif #playlist > 0 then
            rotate()
        end
    end

    publish_state()
end

-- ==========================================================================
-- Callbacks de OBS
-- ==========================================================================

function script_description()
    return
    "<b>OBS Automation Manager — Autopilot</b><br><br>" ..
    "Mantiene la rotación de escenas activa cuando la app cliente se " ..
    "desconecta o la laptop se apaga.<br><br>" ..
    "Config: text source oculto <b>" .. CONFIG_SOURCE .. "</b><br>" ..
    "Estado: text source oculto <b>" .. STATE_SOURCE .. "</b><br><br>" ..
    "No requiere configuración manual — la app cliente se encarga."
end

function script_load(settings)
    log_info("cargando v" .. SCRIPT_VERSION)
    -- Asegurar que los text sources del buzón existan.
    if read_text_source(CONFIG_SOURCE) == "" then
        write_text_source(CONFIG_SOURCE, "")
    end
    write_text_source(STATE_SOURCE, "{\"script_version\":\"" .. SCRIPT_VERSION .. "\",\"mode\":\"standby\"}")

    -- Registrar timers
    obs.timer_add(tick_config, TICK_CONFIG_MS)
    obs.timer_add(tick_rotation, TICK_ROTATION_MS)
    log_info("timers armados; a la espera de config de la app")
end

function script_unload()
    obs.timer_remove(tick_config)
    obs.timer_remove(tick_rotation)
    log_info("descargado")
end
