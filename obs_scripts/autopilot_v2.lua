-- autopilot_v2.lua — Rotador multi-canal autonomo dentro de OBS
--
-- Parte del OBS Automation Manager (rama v2.x). Portado desde la rama
-- v1.8.x (release/v1.8.x-autopilot/obs_scripts/autopilot.lua) para
-- soportar N canales independientes simultaneos — cada uno con su
-- propia playlist, modo de rotacion y handoff.
--
-- Se instala UNA VEZ en el OBS del servidor mediante Tools -> Scripts
-- -> +. Convive sin conflicto con un posible autopilot.lua v1 en el
-- mismo servidor: usa pares de buzones distintos (sufijo _v2).
--
-- Buzones:
--   __autopilot_config_v2__  — la app escribe JSON con canales[] + hb.
--   __autopilot_state_v2__   — este script publica JSON con estado por canal.
--
-- Dos modos de rotacion por canal:
--   program_global  — llama obs_frontend_set_current_scene. Pensado
--                     para el Canal Principal legacy (canal_id = -1).
--   scene_items     — llama obs_sceneitem_set_visible dentro de una
--                     escena contenedora. Pensado para canales
--                     multi-salida que emiten UDP vIa un filtro
--                     Source Record anclado a esa escena.
--
-- Mantenimiento adicional: en cada tick, por cada canal con
-- filter_name, verifica que el filtro Source Record este habilitado y
-- lo re-habilita si lo encuentra off (defensa contra apagados
-- accidentales mientras la app no esta).
--
-- Protocolo JSON detallado: obs_scripts/PROTOCOL_v2.md
--
-- Contenido elaborado con apoyo de IA (TD-NCI-013 num. 5.2)

local obs = obslua

-- ==========================================================================
-- Constantes
-- ==========================================================================

local SCRIPT_VERSION = "2.0.0"
local PROTOCOL_VERSION = 2
local CONFIG_SOURCE = "__autopilot_config_v2__"
local STATE_SOURCE = "__autopilot_state_v2__"

-- Modos de rotacion soportados.
local MODE_PROGRAM_GLOBAL = "program_global"
local MODE_SCENE_ITEMS = "scene_items"

-- Cadencia de los timers internos.
local TICK_ROTATION_MS = 1000     -- 1s: countdown + rotacion + publish state
local TICK_CONFIG_MS = 500        -- 500ms: chequeo de config nueva

-- Sin heartbeat de la app por mas de N segundos → el script toma control.
local HEARTBEAT_TIMEOUT_SEC = 30

-- Cuando ningun item esta en su ventana horaria, esperar este intervalo
-- antes de volver a chequear.
local RETRY_WHEN_NO_ACTIVE_SEC = 60

-- ==========================================================================
-- Estado interno
-- ==========================================================================

-- rotator_states keyed por canal_id (int). Cada entry:
--   {
--     canal_id, modo,
--     scene_name,            -- solo en modo scene_items
--     filter_name,           -- opcional, solo en modo scene_items
--     playlist = [{...}],    -- items del canal
--     active_index,          -- 1-indexed; 0 = ninguno
--     seconds_remaining,
--     last_rotation_at,
--   }
local rotator_states = {}

local last_config_version = 0
local last_heartbeat_epoch = 0     -- os.time() del ultimo heartbeat fresco
local last_heartbeat_str = ""      -- valor del app_heartbeat_at anterior
local mode = "standby"             -- "standby" | "active"

-- Contador de ticks para emitir un log "sigo vivo" cada minuto.
local tick_count = 0

-- Referencias vivas a los text sources del buzon. Guardadas en globals
-- durante toda la vida del script (sin ref viva, OBS los recolecta
-- porque no estan en ninguna scene). Se liberan en script_unload.
local config_source_ref = nil
local state_source_ref = nil

-- ==========================================================================
-- Utilidades
-- ==========================================================================

local function log_info(msg)
    obs.script_log(obs.LOG_INFO, "[autopilot_v2] " .. msg)
end

local function log_warn(msg)
    obs.script_log(obs.LOG_WARNING, "[autopilot_v2] " .. msg)
end

local function now_iso()
    return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

-- Test si el bit N-esimo (0-indexed) esta seteado en value.
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

-- Devuelve true si el item esta dentro de su ventana horaria configurada.
-- Mismo criterio que views/schedule_widget.is_scene_active_now en la app.
local function is_in_window(active_days, time_start, time_end)
    active_days = active_days or 127
    if active_days == 0 then active_days = 127 end
    local now = os.date("*t")
    -- Lua os.date wday: 1=domingo..7=sabado. Convertir a bit 0=lunes..6=domingo.
    local wday_bit = (now.wday - 2) % 7
    if not has_bit(active_days, wday_bit) then
        return false
    end
    local start_min = hhmm_to_min(time_start)
    local end_min = hhmm_to_min(time_end)
    if start_min == nil or end_min == nil then
        return true  -- sin ventana horaria → siempre activa (con dia ok)
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

local function create_text_source(name, initial_text)
    local settings = obs.obs_data_create()
    obs.obs_data_set_string(settings, "text", initial_text or "")
    local source = obs.obs_source_create("text_gdiplus_v3", name, settings, nil)
    if source == nil then
        source = obs.obs_source_create("text_gdiplus_v2", name, settings, nil)
    end
    obs.obs_data_release(settings)
    if source == nil then
        log_warn("no se pudo crear text source: " .. name)
    else
        log_info("creado text source: " .. name)
    end
    return source
end

local function ensure_text_source(name, initial_text)
    local existing = obs.obs_get_source_by_name(name)
    if existing ~= nil then
        return existing
    end
    return create_text_source(name, initial_text)
end

local function read_source_text(source)
    if source == nil then return "" end
    local settings = obs.obs_source_get_settings(source)
    local text = obs.obs_data_get_string(settings, "text") or ""
    obs.obs_data_release(settings)
    return text
end

local function write_source_text(source, text)
    if source == nil then return end
    local settings = obs.obs_data_create()
    obs.obs_data_set_string(settings, "text", text or "")
    obs.obs_source_update(source, settings)
    obs.obs_data_release(settings)
end

-- ==========================================================================
-- Rotacion por modo
-- ==========================================================================

-- Modo program_global: activa `scene_name` como escena de Program en OBS.
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

-- Modo scene_items: dentro de `scene_name`, muestra solo el scene item
-- con id = target_item_id y oculta el resto de ids listados en la
-- playlist del canal. Deja intactos los scene items que no esten en la
-- playlist (ej: placeholders o decorados fijos).
local function activate_scene_item(scene_name, playlist, target_item_id)
    local parent_source = obs.obs_get_source_by_name(scene_name)
    if parent_source == nil then
        log_warn("escena contenedora no existe: " .. scene_name)
        return false
    end
    local scene = obs.obs_scene_from_source(parent_source)
    if scene == nil then
        log_warn("source no es scene: " .. scene_name)
        obs.obs_source_release(parent_source)
        return false
    end

    local toggled = 0
    for _, item in ipairs(playlist) do
        local item_id = item.scene_item_id or 0
        if item_id > 0 then
            local sceneitem = obs.obs_scene_find_sceneitem_by_id(scene, item_id)
            if sceneitem ~= nil then
                local visible = (item_id == target_item_id)
                obs.obs_sceneitem_set_visible(sceneitem, visible)
                toggled = toggled + 1
            end
        end
    end
    obs.obs_source_release(parent_source)

    if toggled == 0 then
        log_warn("ningun scene item encontrado en '" .. scene_name ..
                 "' para los ids de la playlist")
        return false
    end
    return true
end

-- Mantiene habilitado el filtro Source Record del canal (si tiene uno
-- configurado). Defensa contra apagados mientras la app no esta.
local function ensure_filter_enabled(scene_name, filter_name)
    if scene_name == nil or scene_name == "" then return end
    if filter_name == nil or filter_name == "" then return end
    local parent_source = obs.obs_get_source_by_name(scene_name)
    if parent_source == nil then return end
    local filter = obs.obs_source_get_filter_by_name(parent_source, filter_name)
    if filter ~= nil then
        if not obs.obs_source_enabled(filter) then
            obs.obs_source_set_enabled(filter, true)
            log_info("filtro re-habilitado: " .. scene_name .. "/" .. filter_name)
        end
        obs.obs_source_release(filter)
    end
    obs.obs_source_release(parent_source)
end

-- Devuelve el indice (1-indexed) del proximo item que esta en ventana
-- horaria, empezando por (active_index + 1) y dando la vuelta. Devuelve
-- nil si nada esta activo ahora.
local function pick_next_in_window(state)
    local n = #state.playlist
    if n == 0 then return nil end
    local start = state.active_index > 0 and state.active_index or 0
    for offset = 1, n do
        local candidate = ((start - 1 + offset) % n) + 1
        local entry = state.playlist[candidate]
        if is_in_window(entry.active_days, entry.active_time_start, entry.active_time_end) then
            return candidate
        end
    end
    return nil
end

-- Rota el canal al siguiente item. Si nada esta en ventana, agenda retry.
local function rotate_canal(state)
    local idx = pick_next_in_window(state)
    if idx == nil then
        state.active_index = 0
        state.seconds_remaining = RETRY_WHEN_NO_ACTIVE_SEC
        log_info("canal " .. state.canal_id ..
                 ": nada en ventana; reintenta en " ..
                 RETRY_WHEN_NO_ACTIVE_SEC .. "s")
        return
    end
    state.active_index = idx
    local entry = state.playlist[idx]
    state.seconds_remaining = entry.duration_seg or 20
    if state.seconds_remaining < 1 then state.seconds_remaining = 1 end

    local ok = false
    if state.modo == MODE_PROGRAM_GLOBAL then
        ok = activate_scene(entry.name)
    elseif state.modo == MODE_SCENE_ITEMS then
        ok = activate_scene_item(
            state.scene_name, state.playlist, entry.scene_item_id or 0)
    else
        log_warn("canal " .. state.canal_id ..
                 ": modo desconocido '" .. tostring(state.modo) .. "'")
    end

    if ok then
        state.last_rotation_at = now_iso()
        log_info("canal " .. state.canal_id .. " rotate → '" ..
                 entry.name .. "' (" .. state.seconds_remaining .. "s)")
    end
end

-- ==========================================================================
-- Publicacion de estado
-- ==========================================================================

local function publish_state()
    local data = obs.obs_data_create()
    obs.obs_data_set_string(data, "script_version", SCRIPT_VERSION)
    obs.obs_data_set_int(data, "protocol_version", PROTOCOL_VERSION)
    obs.obs_data_set_string(data, "mode", mode)
    obs.obs_data_set_string(data, "updated_at", now_iso())
    obs.obs_data_set_int(data, "last_config_version", last_config_version)

    local arr = obs.obs_data_array_create()
    for _, state in pairs(rotator_states) do
        local entry = obs.obs_data_create()
        obs.obs_data_set_int(entry, "canal_id", state.canal_id)
        obs.obs_data_set_string(entry, "modo_rotacion", state.modo)
        obs.obs_data_set_int(entry, "active_index", state.active_index)
        obs.obs_data_set_int(entry, "seconds_remaining", state.seconds_remaining)
        obs.obs_data_set_string(entry, "last_rotation_at", state.last_rotation_at or "")
        obs.obs_data_set_int(entry, "playlist_size", #state.playlist)

        if state.modo == MODE_PROGRAM_GLOBAL then
            local active_name = ""
            if state.active_index >= 1 and state.active_index <= #state.playlist then
                active_name = state.playlist[state.active_index].name
            end
            obs.obs_data_set_string(entry, "active_scene", active_name)
        elseif state.modo == MODE_SCENE_ITEMS then
            obs.obs_data_set_string(entry, "scene_name", state.scene_name or "")
            local active_id = 0
            if state.active_index >= 1 and state.active_index <= #state.playlist then
                active_id = state.playlist[state.active_index].scene_item_id or 0
            end
            obs.obs_data_set_int(entry, "active_scene_item_id", active_id)
        end

        obs.obs_data_array_push_back(arr, entry)
        obs.obs_data_release(entry)
    end
    obs.obs_data_set_array(data, "canales", arr)
    obs.obs_data_array_release(arr)

    local json = obs.obs_data_get_json(data)
    obs.obs_data_release(data)
    write_source_text(state_source_ref, json)
end

-- ==========================================================================
-- Ingestion de config desde el buzon
-- ==========================================================================

-- Parsea un item de playlist. Modo scene_items incluye scene_item_id.
local function parse_item(item)
    return {
        name = obs.obs_data_get_string(item, "name") or "",
        scene_item_id = obs.obs_data_get_int(item, "scene_item_id"),
        duration_seg = obs.obs_data_get_int(item, "duration_seg"),
        active_days = obs.obs_data_get_int(item, "active_days"),
        active_time_start = obs.obs_data_get_string(item, "active_time_start"),
        active_time_end = obs.obs_data_get_string(item, "active_time_end"),
    }
end

-- Parsea un canal del array canales[]. Devuelve nil si invalido.
local function parse_canal(canal_data, existing_state)
    local canal_id = obs.obs_data_get_int(canal_data, "canal_id")
    local modo = obs.obs_data_get_string(canal_data, "modo_rotacion") or ""
    if modo ~= MODE_PROGRAM_GLOBAL and modo ~= MODE_SCENE_ITEMS then
        log_warn("canal con modo invalido: '" .. modo .. "'; omitido")
        return nil
    end

    local scene_name = obs.obs_data_get_string(canal_data, "scene_name") or ""
    local filter_name = obs.obs_data_get_string(canal_data, "filter_name") or ""
    if modo == MODE_SCENE_ITEMS and scene_name == "" then
        log_warn("canal " .. canal_id .. " modo scene_items sin scene_name; omitido")
        return nil
    end

    local playlist = {}
    local arr = obs.obs_data_get_array(canal_data, "playlist")
    if arr ~= nil then
        local count = obs.obs_data_array_count(arr)
        for i = 0, count - 1 do
            local item = obs.obs_data_array_item(arr, i)
            table.insert(playlist, parse_item(item))
            obs.obs_data_release(item)
        end
        obs.obs_data_array_release(arr)
    end

    -- Preservar progreso del canal si ya existia (republicacion con
    -- misma estructura). Si cambio el tamano o el modo, resetear.
    local active_index = 0
    local seconds_remaining = 0
    local last_rotation_at = ""
    if existing_state ~= nil
       and existing_state.modo == modo
       and #existing_state.playlist == #playlist then
        active_index = existing_state.active_index or 0
        seconds_remaining = existing_state.seconds_remaining or 0
        last_rotation_at = existing_state.last_rotation_at or ""
    end

    -- Handoff explicito tiene precedencia sobre lo preservado.
    local handoff = obs.obs_data_get_obj(canal_data, "handoff")
    if handoff ~= nil then
        local h_remaining = obs.obs_data_get_int(handoff, "seconds_remaining")
        if h_remaining > 0 then
            if modo == MODE_PROGRAM_GLOBAL then
                local h_scene = obs.obs_data_get_string(handoff, "active_scene") or ""
                if h_scene ~= "" then
                    for i, entry in ipairs(playlist) do
                        if entry.name == h_scene then
                            active_index = i
                            seconds_remaining = h_remaining
                            log_info("canal " .. canal_id ..
                                     " handoff: '" .. h_scene ..
                                     "' con " .. h_remaining .. "s")
                            break
                        end
                    end
                end
            else  -- MODE_SCENE_ITEMS
                local h_index = obs.obs_data_get_int(handoff, "active_index")
                if h_index >= 1 and h_index <= #playlist then
                    active_index = h_index
                    seconds_remaining = h_remaining
                    log_info("canal " .. canal_id ..
                             " handoff: index=" .. h_index ..
                             " con " .. h_remaining .. "s")
                end
            end
        end
        obs.obs_data_release(handoff)
    end

    return {
        canal_id = canal_id,
        modo = modo,
        scene_name = scene_name,
        filter_name = filter_name,
        playlist = playlist,
        active_index = active_index,
        seconds_remaining = seconds_remaining,
        last_rotation_at = last_rotation_at,
    }
end

local function ingest_config()
    local text = read_source_text(config_source_ref)
    if text == nil or text == "" then return end
    local data = obs.obs_data_create_from_json(text)
    if data == nil then return end

    local proto = obs.obs_data_get_int(data, "protocol_version")
    if proto ~= 0 and proto ~= PROTOCOL_VERSION then
        log_warn("protocol_version " .. proto ..
                 " no soportada; esperado " .. PROTOCOL_VERSION ..
                 ". Mantengo config anterior.")
        obs.obs_data_release(data)
        return
    end

    local version = obs.obs_data_get_int(data, "version")

    -- Heartbeat: solo marcar como fresco si el valor cambio desde la
    -- ultima lectura. Si el string es el mismo (la app ya no esta
    -- escribiendo), no refrescar — asi el timeout puede vencer y el
    -- script pasa a mode=active.
    local heartbeat_str = obs.obs_data_get_string(data, "app_heartbeat_at") or ""
    if heartbeat_str ~= "" and heartbeat_str ~= last_heartbeat_str then
        last_heartbeat_epoch = os.time()
        last_heartbeat_str = heartbeat_str
    end

    -- Solo re-cargar canales si version subio.
    if version <= last_config_version then
        obs.obs_data_release(data)
        return
    end

    local canales_arr = obs.obs_data_get_array(data, "canales")
    if canales_arr ~= nil then
        local new_states = {}
        local count = obs.obs_data_array_count(canales_arr)
        for i = 0, count - 1 do
            local canal_data = obs.obs_data_array_item(canales_arr, i)
            local parsed = parse_canal(
                canal_data, rotator_states[obs.obs_data_get_int(canal_data, "canal_id")])
            if parsed ~= nil then
                new_states[parsed.canal_id] = parsed
            end
            obs.obs_data_release(canal_data)
        end
        obs.obs_data_array_release(canales_arr)
        rotator_states = new_states
    end

    last_config_version = version
    obs.obs_data_release(data)

    local n_canales = 0
    for _ in pairs(rotator_states) do n_canales = n_canales + 1 end
    log_info("config v" .. version .. " cargada (" .. n_canales .. " canales)")
end

-- ==========================================================================
-- Ticks
-- ==========================================================================

local function tick_config()
    ingest_config()
end

local function tick_rotation()
    -- Determinar modo segun edad del ultimo heartbeat.
    if last_heartbeat_epoch > 0 and
       (os.time() - last_heartbeat_epoch) < HEARTBEAT_TIMEOUT_SEC then
        mode = "standby"
    else
        mode = "active"
    end

    -- Siempre mantener los filtros Source Record habilitados — incluso
    -- en standby, el filtro no debe quedar off accidentalmente.
    for _, state in pairs(rotator_states) do
        ensure_filter_enabled(state.scene_name, state.filter_name)
    end

    if mode == "active" then
        for _, state in pairs(rotator_states) do
            if state.seconds_remaining > 0 then
                state.seconds_remaining = state.seconds_remaining - 1
                if state.seconds_remaining == 0 then
                    rotate_canal(state)
                end
            elseif #state.playlist > 0 then
                rotate_canal(state)
            end
        end
    end

    publish_state()

    -- Heartbeat de log cada 60s — confirma que los timers no se
    -- congelaron. Formato compacto para no spamear.
    tick_count = tick_count + 1
    if tick_count % 60 == 0 then
        local n_canales = 0
        for _ in pairs(rotator_states) do n_canales = n_canales + 1 end
        log_info(string.format(
            "vivo: mode=%s, canales=%d, last_config_v=%d",
            mode, n_canales, last_config_version
        ))
    end
end

-- ==========================================================================
-- Callbacks de OBS
-- ==========================================================================

function script_description()
    return
    "<b>OBS Automation Manager — Autopilot v2 (multi-canal)</b><br><br>" ..
    "Mantiene la rotacion de N canales independientes activa cuando la " ..
    "app cliente se desconecta o la laptop se apaga.<br><br>" ..
    "Config: text source oculto <b>" .. CONFIG_SOURCE .. "</b><br>" ..
    "Estado: text source oculto <b>" .. STATE_SOURCE .. "</b><br><br>" ..
    "Convive con el Autopilot v1 (<i>autopilot.lua</i>) si esta " ..
    "instalado — cada version usa sus propios buzones.<br><br>" ..
    "No requiere configuracion manual — la app cliente se encarga."
end

function script_load(settings)
    log_info("cargando v" .. SCRIPT_VERSION)
    -- Reset defensivo: si el script esta siendo recargado, remover
    -- timers zombi del load anterior antes de registrar los nuevos.
    -- Sin esto, despues de varios reloads podrIamos tener multiples
    -- callbacks de tick_config y tick_rotation en paralelo (o peor,
    -- referencias a funciones antiguas que ya no existen).
    obs.timer_remove(tick_config)
    obs.timer_remove(tick_rotation)
    tick_count = 0

    -- Crear (o adoptar) los text sources del buzon, guardando ref viva.
    config_source_ref = ensure_text_source(CONFIG_SOURCE, "")
    state_source_ref = ensure_text_source(
        STATE_SOURCE,
        "{\"script_version\":\"" .. SCRIPT_VERSION ..
        "\",\"protocol_version\":2,\"mode\":\"standby\",\"canales\":[]}"
    )

    -- Registrar timers frescos.
    obs.timer_add(tick_config, TICK_CONFIG_MS)
    obs.timer_add(tick_rotation, TICK_ROTATION_MS)
    log_info("timers armados; a la espera de config v2 de la app")
end

function script_unload()
    obs.timer_remove(tick_config)
    obs.timer_remove(tick_rotation)
    if config_source_ref ~= nil then
        obs.obs_source_release(config_source_ref)
        config_source_ref = nil
    end
    if state_source_ref ~= nil then
        obs.obs_source_release(state_source_ref)
        state_source_ref = nil
    end
    log_info("descargado")
end
