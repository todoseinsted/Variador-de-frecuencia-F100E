#!/usr/bin/env python3
"""Control Modbus RTU de un variador FC100E desde Raspberry PLC 19R."""

from __future__ import annotations

import argparse
import struct
import sys
import time

try:
    import serial
except ImportError:
    print("Falta pyserial. Instale: sudo apt install python3-serial", file=sys.stderr)
    raise SystemExit(2)


# Mapa Modbus del FC100E. No es el mapa del FC100 antiguo con RJ-11.
REG_SETPOINT = 0x1000
REG_FREQUENCY = 0x1001
REG_DC_BUS_VOLTAGE = 0x1002
REG_OUTPUT_VOLTAGE = 0x1003
REG_OUTPUT_CURRENT = 0x1004
REG_COMMAND = 0x2000
REG_STATUS = 0x3000
REG_FAULT = 0x8000

COMMANDS = {
    "directa": 0x0001,
    "reversa": 0x0002,
    "jog-directa": 0x0003,
    "jog-reversa": 0x0004,
    "parada-libre": 0x0005,
    "parar": 0x0006,
    "reset-falla": 0x0007,
}
STATUS = {1: "operando en directa", 2: "operando en reversa", 3: "detenido"}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def exchange(port: serial.Serial, body: bytes, expected_length: int) -> bytes:
    request = body + struct.pack("<H", crc16(body))
    port.reset_input_buffer()
    port.write(request)
    port.flush()
    response = port.read(expected_length)
    # El manual exige un silencio entre tramas de al menos 10 ms.
    time.sleep(0.012)
    if len(response) != expected_length:
        raise TimeoutError(f"respuesta incompleta: {len(response)}/{expected_length} bytes")
    if crc16(response[:-2]) != struct.unpack("<H", response[-2:])[0]:
        raise ValueError("CRC incorrecto")
    if response[0] != body[0]:
        raise ValueError(f"respondio ID {response[0]}, se esperaba {body[0]}")
    if response[1] & 0x80:
        raise ValueError(f"excepcion Modbus {response[2]}")
    return response


def read_words(port: serial.Serial, slave: int, address: int, count: int = 1) -> list[int]:
    body = struct.pack(">BBHH", slave, 3, address, count)
    response = exchange(port, body, 5 + 2 * count)
    if response[1] != 3 or response[2] != 2 * count:
        raise ValueError(f"respuesta de lectura inesperada: {response.hex(' ')}")
    return list(struct.unpack(f">{count}H", response[3:-2]))


def write_word(port: serial.Serial, slave: int, address: int, value: int) -> None:
    body = struct.pack(">BBHH", slave, 6, address, value & 0xFFFF)
    response = exchange(port, body, 8)
    if response[:-2] != body:
        raise ValueError(f"eco de escritura inesperado: {response.hex(' ')}")


def show_status(port: serial.Serial, slave: int) -> None:
    frequency = read_words(port, slave, REG_FREQUENCY)[0] / 100
    dc_bus = read_words(port, slave, REG_DC_BUS_VOLTAGE)[0] / 10
    output_voltage = read_words(port, slave, REG_OUTPUT_VOLTAGE)[0]
    current = read_words(port, slave, REG_OUTPUT_CURRENT)[0] / 100
    state = read_words(port, slave, REG_STATUS)[0]
    fault = read_words(port, slave, REG_FAULT)[0]
    print(
        f"Estado: {STATUS.get(state, f'codigo 0x{state:04X}')} | "
        f"f={frequency:.2f} Hz | U={output_voltage} V | I={current:.2f} A | "
        f"bus_CC={dc_bus:.1f} V | falla=0x{fault:04X}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", default="/dev/ttySC2", help="RS-485 1 del PLC 19R")
    parser.add_argument("--id", type=int, default=1, help="PD-02")
    parser.add_argument("--baudios", type=int, choices=(300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600), default=9600)
    parser.add_argument("--paridad", choices=("N", "E", "O"), default="N")
    sub = parser.add_subparsers(dest="accion")
    sub.add_parser("estado", help="leer mediciones; es la accion predeterminada")
    frequency = sub.add_parser("frecuencia", help="escribir consigna en Hz")
    frequency.add_argument("hz", type=float)
    frequency.add_argument("--maxima", type=float, default=50.0, help="limite de seguridad")
    test = sub.add_parser("prueba", help="marcha directa temporizada y parada garantizada")
    test.add_argument("--hz", type=float, default=5.0)
    test.add_argument("--segundos", type=float, default=5.0)
    test.add_argument("--maxima", type=float, default=50.0, help="debe coincidir con P0-10")
    for command in COMMANDS:
        sub.add_parser(command)
    raw_read = sub.add_parser("leer", help="leer un registro hexadecimal para diagnostico")
    raw_read.add_argument("direccion", type=lambda value: int(value, 0))
    return parser.parse_args()


def confirm_motion(action: str) -> bool:
    print(f"ADVERTENCIA: '{action}' puede poner el motor en movimiento.")
    return input("Escriba MOVER para enviar la orden: ").strip() == "MOVER"


def main() -> int:
    args = parse_args()
    if not 1 <= args.id <= 247:
        print("El ID/PD-02 debe estar entre 1 y 247.", file=sys.stderr)
        return 2
    parity = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}[args.paridad]
    try:
        with serial.Serial(
            args.puerto, args.baudios, bytesize=serial.EIGHTBITS,
            parity=parity, stopbits=serial.STOPBITS_ONE, timeout=1,
        ) as port:
            if args.accion in (None, "estado"):
                show_status(port, args.id)
            elif args.accion == "leer":
                value = read_words(port, args.id, args.direccion)[0]
                print(f"0x{args.direccion:04X} = {value} (0x{value:04X})")
            elif args.accion == "frecuencia":
                if args.maxima <= 0 or not 0 <= args.hz <= args.maxima:
                    raise ValueError(f"frecuencia fuera de 0..{args.maxima:g} Hz")
                # 10000 representa 100 % de P0-10 en el FC100E.
                value = round(args.hz / args.maxima * 10000)
                write_word(port, args.id, REG_SETPOINT, value)
                print(f"Consigna enviada: {args.hz:.2f} Hz ({value}/10000 de P0-10).")
            elif args.accion == "prueba":
                if args.maxima <= 0 or not 0 < args.hz <= args.maxima or args.segundos <= 0:
                    raise ValueError("hz/segundos fuera de rango")
                if not confirm_motion(f"prueba a {args.hz:g} Hz durante {args.segundos:g} s"):
                    print("Orden cancelada.")
                    return 1
                value = round(args.hz / args.maxima * 10000)
                try:
                    write_word(port, args.id, REG_SETPOINT, value)
                    write_word(port, args.id, REG_COMMAND, COMMANDS["directa"])
                    print("Marcha enviada.")
                    time.sleep(args.segundos)
                    show_status(port, args.id)
                finally:
                    write_word(port, args.id, REG_COMMAND, COMMANDS["parar"])
                    print("Parada enviada.")
            else:
                if args.accion in ("directa", "reversa") and not confirm_motion(args.accion):
                    print("Orden cancelada.")
                    return 1
                write_word(port, args.id, REG_COMMAND, COMMANDS[args.accion])
                print(f"Comando enviado: {args.accion}.")
        return 0
    except PermissionError:
        print(f"Sin permiso para {args.puerto}; agregue el usuario al grupo dialout.", file=sys.stderr)
    except (OSError, TimeoutError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
