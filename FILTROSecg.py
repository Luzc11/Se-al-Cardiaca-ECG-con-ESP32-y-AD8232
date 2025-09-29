from machine import ADC, Pin, Timer 
import time, sys, uselect

# -------------------------------
# Configuración
# -------------------------------
FS = 250                     # Frecuencia de muestreo
DT_MS = int(1000 / FS)       # Periodo en ms
N = 5                        # Ventana de promedio/mediana
ALPHA = 0.15                 # Constante filtro exponencial
SKIP = 10                    # Cada cuántas muestras se imprime
FILE_NAME = "ecg_data.txt"   # Nombre del archivo donde guardar

adc = ADC(Pin(34))           # Entrada en GPIO34
adc.atten(ADC.ATTN_11DB)     # Rango hasta 3.3V
adc.width(ADC.WIDTH_12BIT)   # Resolución 12 bits (0-4095)

led = Pin(2, Pin.OUT)        # LED indicador
led.on()

# -------------------------------
# Variables
# -------------------------------
ring = [0]*N
idx = 0
llen = 0
ema = None
new = False
valor = 0
count = 0

# Estado de visualización
modo = 1   # 1=solo RAW, 2=RAW+PROM, 3=RAW+MED, 4=RAW+EXP, 5=solo FIL

# Buffer para almacenamiento en archivo
buffer_lines = []
FLUSH_EVERY = 50   # cada cuántas muestras escribir en archivo

# -------------------------------
# Timer ISR
# -------------------------------
def handler(t):
    global valor, new
    valor = adc.read()
    new = True

timer = Timer(0)
timer.init(period=DT_MS, mode=Timer.PERIODIC, callback=handler)

# -------------------------------
# Polling teclado
# -------------------------------
poll = uselect.poll()
poll.register(sys.stdin, uselect.POLLIN)

print("\n--- Selección de visualización ---")
print("1 → Solo RAW")
print("2 → RAW + PROM")
print("3 → RAW + MED")
print("4 → RAW + EXP")
print("5 → Solo FILTRADA (según nivel máximo)")
print("----------------------------------")

try:
    while True:
        # --- Control desde teclado ---
        if poll.poll(0):
            cmd = sys.stdin.readline().strip()
            if cmd in ["1", "2", "3", "4", "5"]:
                modo = int(cmd)
                print(f"Modo activo: {modo}")

        # --- Nueva muestra ---
        if new:
            new = False
            v = valor   # señal cruda
            salida = v  # inicio cascada
            etiqueta = "RAW"

            # Buffer para filtros
            ring[idx] = salida
            idx = (idx + 1) % N
            llen = min(llen + 1, N)
            window = ring[:llen]

            # Filtros en cascada
            if modo >= 2 or modo == 5:
                salida = sum(window) // llen
                etiqueta = "PROM"

            if modo >= 3 or modo == 5:
                salida = sorted(window)[llen // 2]
                etiqueta = "MED"

            if modo >= 4 or modo == 5:
                ema = salida if ema is None else int(ALPHA*salida + (1-ALPHA)*ema)
                salida = ema
                etiqueta = "EXP"

            # --- Construcción de salida ---
            count += 1
            if count >= SKIP:
                count = 0
                if modo == 1:
                    linea = f"RAW:{v}\n"
                elif modo in [2, 3, 4]:
                    linea = f"RAW:{v} | {etiqueta}:{salida}\n"
                elif modo == 5:
                    linea = f"{etiqueta}:{salida}\n"

                print(linea.strip())
                buffer_lines.append(linea)

                # Guardar cada cierto número de líneas
                if len(buffer_lines) >= FLUSH_EVERY:
                    with open(FILE_NAME, "a") as f:
                        f.write(''.join(buffer_lines))
                    buffer_lines.clear()

            time.sleep_ms(1)

except KeyboardInterrupt:
    pass
finally:
    # Guardar lo pendiente
    if buffer_lines:
        with open(FILE_NAME, "a") as f:
            f.write(''.join(buffer_lines))
        buffer_lines.clear()

    timer.deinit()
    led.off()
    print("Programa detenido. Datos guardados en", FILE_NAME)
