import calendar
import datetime

class CalendarModel:
    def weeks_in_month(self, target_date=None):
        """Devuelve cuántas filas ocupa el mes en un calendario que arranca en domingo.

        Típicamente 5 o 6. Febrero de 28 días empezando en domingo devuelve 4.
        """
        if target_date is None:
            target_date = datetime.date.today()
        first_weekday, ndays = calendar.monthrange(target_date.year, target_date.month)
        start_col = (first_weekday + 1) % 7  # Dom=0…Sáb=6
        total_cells = start_col + ndays
        return (total_cells + 6) // 7  # ceil

    def calculate_position(self, x_start, y_start, x_spacing, y_spacing, target_date=None):
        """
        Calcula la coordenada (X, Y) exacta para un día en el calendario.
        """
        if target_date is None:
            target_date = datetime.date.today()

        year = target_date.year
        month = target_date.month
        day = target_date.day

        # calendar.monthrange devuelve (dia_semana_inicial, total_dias)
        # Nota: En Python, Lunes = 0, Domingo = 6.
        first_weekday, _ = calendar.monthrange(year, month)

        # Convertimos para que nuestro Domingo sea la columna 0 (como en los diseños del cliente)
        start_col = (first_weekday + 1) % 7

        # Calculamos la columna y fila actual (restamos 1 porque los días empiezan en 1)
        current_col = (start_col + (day - 1)) % 7
        current_row = (start_col + (day - 1)) // 7

        # Posición final: Origen + (Índice * Espaciado)
        x_pos = x_start + (current_col * x_spacing)
        y_pos = y_start + (current_row * y_spacing)

        return x_pos, y_pos