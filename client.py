# Battleship game client

import argparse
import json
import socket
import sys
import time
from typing import Dict, Optional


BOARD_SIZE = 12
SHIPS = (
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
)


class BattleshipClient:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.receive_buffer = bytearray()
        self.player_id: Optional[int] = None
        self.phase = "CONNECTING"
        self.board = [["~" for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.ship_locations: Dict[str, list[tuple[int, int]]] = {}
        self.placed_ship_names: set[str] = set()
        self.active_player: Optional[int] = None

    def packet(self, packet_type: str, contents: object = None) -> dict:
        return {
            "packet_type": packet_type,
            "player_id": f"P{self.player_id + 1}" if self.player_id is not None else "UNKNOWN",
            "contents": contents if contents is not None else {},
            "timestamp": int(time.time()),
        }

    def connect(self) -> bool:
        try:
            resolved_ip = socket.gethostbyname(self.host)
        except socket.gaierror:
            print(
                f"[ERROR] Unable to resolve DNS hostname '{self.host}'. "
                "Check DNS configuration or verify the hostname spelling."
            )
            return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((resolved_ip, self.port))
            sock.settimeout(None)
            self.sock = sock
        except (socket.timeout, ConnectionRefusedError, OSError) as exc:
            print(f"[ERROR] Unable to connect to {resolved_ip}:{self.port}: {exc}")
            return False

        self.send_packet("CONNECT", {"match_id": 123456})
        return True

    def send_packet(self, packet_type: str, contents: object = None) -> None:
        if self.sock is None:
            raise RuntimeError("Client socket is not connected")
        payload = json.dumps(self.packet(packet_type, contents), separators=(",", ":")).encode("utf-8") + b"\n"
        self.sock.sendall(payload)

    def receive_packet(self) -> Optional[dict]:
        if self.sock is None:
            return None
        while b"\n" not in self.receive_buffer:
            try:
                data = self.sock.recv(4096)
            except (ConnectionResetError, BrokenPipeError, socket.timeout, OSError) as exc:
                print(f"\n[ERROR] Server connection failed: {exc}")
                return None
            if not data:
                print("\n[ERROR] Server closed the connection")
                return None
            self.receive_buffer.extend(data)

        line, _, remaining = self.receive_buffer.partition(b"\n")
        self.receive_buffer = bytearray(remaining)
        try:
            packet = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print("[ERROR] Received malformed JSON packet")
            return None
        if not isinstance(packet, dict):
            print("[ERROR] Received an invalid packet")
            return None
        return packet

    def parse_coordinate(self, text: str) -> Optional[tuple[int, int]]:
        text = text.strip().upper()
        if not text:
            return None
        import re
        match = re.fullmatch(r"([A-L])(1|2|3|4|5|6|7|8|9|10|11|12)", text)
        if not match:
            return None
        row = ord(match.group(1)) - ord("A")
        col = int(match.group(2)) - 1
        return row, col

    def print_board(self) -> None:
        print("    " + " ".join(f"{col + 1:2}" for col in range(BOARD_SIZE)))
        for row in range(BOARD_SIZE):
            print(f"{chr(65 + row):>2}  " + " ".join(f"{cell:>2}" for cell in self.board[row]))

    def place_ships(self) -> bool:
        self.phase = "SHIP_PLACEMENT"
        print("\nPlace your ships.")
        print("Coordinates use row/column notation such as A1 or L12.")

        for ship_name, ship_length in SHIPS:
            if ship_name in self.placed_ship_names:
                continue
            while True:
                print(f"\nPlace {ship_name} (length {ship_length})")
                try:
                    coordinate_text = input("  Start coordinate (A1-L12): ").strip()
                    orientation = input("  Orientation (horizontal/vertical): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    self.disconnect()
                    return False

                coordinate = self.parse_coordinate(coordinate_text)
                if coordinate is None:
                    print("[ERROR] Invalid coordinate. Use a value from A1 to L12.")
                    continue
                if orientation not in ("horizontal", "vertical"):
                    print("[ERROR] Orientation must be horizontal or vertical.")
                    continue

                row, col = coordinate
                self.send_packet("PLACE_SHIP", {
                    "ship": ship_name,
                    "coordinates": {"row": row, "col": col},
                    "orientation": orientation,
                })
                response = self.receive_packet()
                if response is None:
                    return False

                packet_type = response.get("packet_type")
                if packet_type == "ERROR":
                    message = response.get("contents", {}).get("message", "Invalid ship placement")
                    print(f"[ERROR] {message}")
                    continue
                if packet_type == "PLACE_ACCEPTED":
                    ship_cells = []
                    for offset in range(ship_length):
                        ship_row = row + offset if orientation == "vertical" else row
                        ship_col = col + offset if orientation == "horizontal" else col
                        ship_cells.append((ship_row, ship_col))
                        self.board[ship_row][ship_col] = "S"
                    self.ship_locations[ship_name] = ship_cells
                    self.placed_ship_names.add(ship_name)
                    print(f"Placed {ship_name}.")
                    break
                if packet_type == "SHIPS_PLACED":
                    self.placed_ship_names.add(ship_name)
                    break
                print(f"[ERROR] Unexpected placement response: {packet_type}")

        self.phase = "WAITING"
        print("\nShips placed. Waiting for both players and the first turn...")
        return True

    def disconnect(self) -> None:
        if self.sock is not None:
            try:
                self.send_packet("DISCONNECT", {"reason": "client exit"})
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            self.sock.close()
            self.sock = None

    def play_turn(self) -> bool:
        print("\nYour Turn")
        while True:
            try:
                text = input("  Guess coordinate (A1-L12): ").strip()
            except (EOFError, KeyboardInterrupt):
                self.disconnect()
                return False
            coordinate = self.parse_coordinate(text)
            if coordinate is None:
                print("[ERROR] Invalid coordinate. Use a value from A1 to L12.")
                continue
            row, col = coordinate
            self.send_packet("PLAYER_TURN", {
                "coordinates": {"row": row, "col": col},
            })
            response = self.receive_packet()
            if response is None:
                return False
            packet_type = response.get("packet_type")
            if packet_type == "ERROR":
                message = response.get("contents", {}).get("message", "Invalid guess")
                print(f"[ERROR] {message}")
                continue
            if packet_type == "TURN_RESULT":
                self.show_turn_result(response)
                return True
            if packet_type == "GAME_OVER":
                self.show_game_over(response)
                return False
            print(f"[ERROR] Unexpected turn response: {packet_type}")

    def show_turn_result(self, packet: dict) -> None:
        contents = packet.get("contents", {})
        shooter = contents.get("shooter")
        coordinate = contents.get("coordinates", {})
        row = coordinate.get("row")
        col = coordinate.get("col")
        result = contents.get("result")
        active = contents.get("active_player")
        self.active_player = active

        if isinstance(row, int) and isinstance(col, int):
            mark = "X" if result == "hit" else "o"
            if shooter == self.player_id:
                self.board[row][col] = mark

        print(
            f"Player {shooter + 1 if isinstance(shooter, int) else '?'} "
            f"guessed {chr(65 + row)}{col + 1}: {result}"
            if isinstance(row, int) and isinstance(col, int)
            else f"Turn result: {result}"
        )
        sunk = contents.get("sunk_ships", [])
        if sunk:
            print(f"Sunk: {', '.join(sunk)}")
        print("Waiting for Player 2..." if active != self.player_id else "Your Turn")
        self.print_board()

    def show_game_over(self, packet: dict) -> None:
        contents = packet.get("contents", {})
        winner = contents.get("winner")
        reason = contents.get("reason", "")
        if winner == self.player_id:
            print("\nGAME OVER: You win!")
        else:
            print("\nGAME OVER: You lose.")
        print(f"Reason: {reason}")

    def run(self) -> int:
        if not self.connect():
            return 1

        print(f"Connected to {self.host}:{self.port}")
        try:
            while True:
                packet = self.receive_packet()
                if packet is None:
                    return 1
                packet_type = packet.get("packet_type")
                contents = packet.get("contents", {})

                if packet_type == "CONN_WAIT":
                    self.player_id = contents.get("player_id", self.player_id)
                    print("Waiting for Player 2...")

                elif packet_type == "CONN_CONFIRM":
                    if isinstance(contents.get("player_id"), int):
                        self.player_id = contents["player_id"]
                    print("Both players connected.")
                    print("Choose a number from 1 to 10.")
                    try:
                        number_text = input("  Player number: ").strip()
                        number = int(number_text)
                    except (EOFError, KeyboardInterrupt):
                        self.disconnect()
                        return 0
                    except ValueError:
                        print("[ERROR] Number must be an integer from 1 to 10.")
                        continue
                    if not 1 <= number <= 10:
                        print("[ERROR] Number must be from 1 to 10.")
                        continue
                    self.send_packet("PLAYER_NUMBER", {"number": number})

                elif packet_type == "GAME_START":
                    self.phase = "SHIP_PLACEMENT"
                    self.active_player = contents.get("active_player")
                    if not self.place_ships():
                        return 0

                elif packet_type == "SHIPS_PLACED":
                    self.phase = "PLAYING"
                    self.active_player = contents.get("active_player")
                    print("\nAll ships are placed. The game begins.")
                    self.print_board()
                    if self.active_player == self.player_id:
                        if not self.play_turn():
                            continue
                    else:
                        print("Waiting for Player 2...")

                elif packet_type == "TURN_RESULT":
                    self.show_turn_result(packet)

                elif packet_type == "GAME_OVER":
                    self.show_game_over(packet)
                    self.disconnect()
                    return 0

                elif packet_type == "ERROR":
                    print(f"[ERROR] {contents.get('message', 'Unknown server error')}")

                else:
                    print(f"[ERROR] Unexpected packet type: {packet_type}")

        except KeyboardInterrupt:
            print("\nDisconnecting.")
            self.disconnect()
            return 0
        finally:
            if self.sock is not None:
                self.sock.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Two-player Battleship client")
    parser.add_argument("-i", "--hostname", required=True, help="Server DNS hostname")
    parser.add_argument("-p", "--port", type=int, required=True, help="Server TCP port")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    return args


def main() -> int:
    args = parse_args()
    client = BattleshipClient(args.hostname, args.port)
    return client.run()


if __name__ == "__main__":
    raise SystemExit(main())
