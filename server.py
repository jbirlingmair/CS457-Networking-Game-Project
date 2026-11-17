# Battleship game server

import argparse
import hashlib
import json
import random
import selectors
import socket
import sys
import types
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Set, Tuple


HOST = "0.0.0.0"
BOARD_SIZE = 12
SHIPS = (
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
)


@dataclass
class Connection:
    addr: Tuple[str, int]
    player_index: Optional[int] = None
    inb: bytearray = field(default_factory=bytearray)
    outb: bytearray = field(default_factory=bytearray)


@dataclass
class Board:
    ships: Dict[str, Set[Tuple[int, int]]] = field(default_factory=dict)
    guesses: Set[Tuple[int, int]] = field(default_factory=set)


class GameServer:
    def __init__(self, port: int) -> None:
        self.port = port
        self.selector = selectors.DefaultSelector()
        self.state = "WAITING_FOR_PLAYERS"
        self.connections: Dict[socket.socket, Connection] = {}
        self.players: Dict[int, socket.socket] = {}
        self.boards: Dict[int, Board] = {0: Board(), 1: Board()}
        self.placed_ships: Dict[int, Set[str]] = {0: set(), 1: set()}
        self.numbers: Dict[int, int] = {}
        self.secret_number = random.randint(1, 10)
        self.active_player: Optional[int] = None
        self.listening_socket: Optional[socket.socket] = None

    def packet(self, packet_type: str, contents: object = None) -> dict:
        return {
            "packet_type": packet_type,
            "player_id": "SERVER",
            "contents": contents if contents is not None else {},
            "timestamp": int(__import__("time").time()),
        }

    def send_packet(self, sock: socket.socket, packet_type: str, contents: object = None) -> None:
        payload = json.dumps(self.packet(packet_type, contents), separators=(",", ":")).encode("utf-8") + b"\n"
        connection = self.connections.get(sock)
        if connection is not None:
            connection.outb.extend(payload)

    def broadcast(self, packet_type: str, contents: object = None) -> None:
        for sock in list(self.players.values()):
            if sock in self.connections:
                self.send_packet(sock, packet_type, contents)

    def send_error(self, sock: socket.socket, message: str) -> None:
        self.send_packet(sock, "ERROR", {"message": message})

    def start(self) -> None:
        listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listening.bind((HOST, self.port))
        listening.listen()
        listening.setblocking(False)
        self.listening_socket = listening
        self.selector.register(listening, selectors.EVENT_READ, data=None)
        print(f"Battleship server listening on {HOST}:{self.port}")

    def accept(self, listening: socket.socket) -> None:
        if len(self.players) >= 2:
            conn, addr = listening.accept()
            conn.setblocking(False)
            data = Connection(addr)
            self.connections[conn] = data
            self.selector.register(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)
            self.send_error(conn, "Match is full")
            return

        conn, addr = listening.accept()
        conn.setblocking(False)
        player_index = 0 if 0 not in self.players else 1
        data = Connection(addr=addr, player_index=player_index)
        self.connections[conn] = data
        self.players[player_index] = conn
        self.selector.register(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)
        print(f"Player {player_index + 1} connected from {addr}")

        if len(self.players) == 1:
            self.state = "WAITING_FOR_PLAYERS"
            self.send_packet(conn, "CONN_WAIT", {"match_id": 123456, "player_id": player_index})
        else:
            self.state = "NUMBER_SELECTION"
            self.secret_number = random.randint(1, 10)
            contents = {"match_id": 123456, "minimum": 1, "maximum": 10, "secret_status": "selected"}
            for index, player_socket in self.players.items():
                player_contents = dict(contents)
                player_contents["player_id"] = index
                self.send_packet(player_socket, "CONN_CONFIRM", player_contents)

    def close_connection(self, sock: socket.socket) -> None:
        connection = self.connections.get(sock)
        if connection is None:
            return

        player_index = connection.player_index
        print(f"Closing connection for Player {player_index + 1 if player_index is not None else 'unknown'}")

        try:
            self.selector.unregister(sock)
        except (KeyError, ValueError):
            pass
        sock.close()
        del self.connections[sock]

        if player_index is not None and self.players.get(player_index) is sock:
            del self.players[player_index]

        if player_index is not None:
            remaining = [p for p in self.players.values() if p in self.connections]
            if remaining and self.state not in ("WAITING_FOR_PLAYERS", "GAME_OVER"):
                self.send_packet(remaining[0], "GAME_OVER", {
                    "winner": 1 - player_index,
                    "reason": "opponent disconnected",
                    "hits": {},
                    "misses": {},
                })
                print(f"Player {2 - player_index} wins by disconnect")
            self.reset_match(keep_connections=True)

    def reset_match(self, keep_connections: bool = True) -> None:
        self.state = "WAITING_FOR_PLAYERS" if len(self.players) > 0 else "WAITING_FOR_PLAYERS"
        self.boards = {0: Board(), 1: Board()}
        self.placed_ships = {0: set(), 1: set()}
        self.numbers = {}
        self.active_player = None
        self.secret_number = random.randint(1, 10)

        if keep_connections and len(self.players) == 1:
            player_index, sock = next(iter(self.players.items()))
            if sock in self.connections:
                self.send_packet(sock, "CONN_WAIT", {"match_id": 123456, "player_id": player_index})

    def receive(self, key: selectors.SelectorKey, mask: int) -> None:
        sock = key.fileobj
        connection = key.data
        if mask & selectors.EVENT_READ:
            try:
                recv_data = sock.recv(4096)
            except (BlockingIOError, InterruptedError):
                recv_data = None
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                print(f"Socket receive error: {exc}")
                self.close_connection(sock)
                return

            if recv_data:
                connection.inb.extend(recv_data)
                self.process_input_buffer(sock, connection)
            else:
                self.close_connection(sock)
                return

        if mask & selectors.EVENT_WRITE:
            if connection.outb:
                try:
                    sent = sock.send(connection.outb)
                    del connection.outb[:sent]
                except (BlockingIOError, InterruptedError):
                    pass
                except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                    print(f"Socket send error: {exc}")
                    self.close_connection(sock)

    def process_input_buffer(self, sock: socket.socket, connection: Connection) -> None:
        while b"\n" in connection.inb:
            line, _, remaining = connection.inb.partition(b"\n")
            connection.inb = bytearray(remaining)
            if not line:
                continue
            try:
                packet = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(sock, "Malformed JSON packet")
                continue
            self.process_packet(sock, connection, packet)

    def process_packet(self, sock: socket.socket, connection: Connection, packet: dict) -> None:
        if not isinstance(packet, dict):
            self.send_error(sock, "Packet must be a JSON object")
            return
        packet_type = packet.get("packet_type")
        contents = packet.get("contents")
        if not isinstance(contents, dict):
            self.send_error(sock, "Packet contents must be a JSON object")
            return

        if packet_type == "DISCONNECT":
            self.close_connection(sock)
            return

        if packet_type == "CONNECT":
            return

        if packet_type == "PLAYER_NUMBER":
            self.handle_player_number(sock, connection, contents)
        elif packet_type == "PLACE_SHIP":
            self.handle_place_ship(sock, connection, contents)
        elif packet_type == "PLAYER_TURN":
            self.handle_player_turn(sock, connection, contents)
        else:
            self.send_error(sock, f"Unexpected packet type '{packet_type}' in state '{self.state}'")

    def handle_player_number(self, sock: socket.socket, connection: Connection, contents: dict) -> None:
        if self.state != "NUMBER_SELECTION":
            self.send_error(sock, "PLAYER_NUMBER is not valid now")
            return
        if connection.player_index is None:
            self.send_error(sock, "Player is not registered")
            return

        player_index = connection.player_index
        if player_index in self.numbers:
            self.send_error(sock, "A number has already been submitted")
            return

        try:
            number = int(contents.get("number"))
        except (TypeError, ValueError):
            self.send_error(sock, "Number must be an integer from 1 to 10")
            return
        if not 1 <= number <= 10:
            self.send_error(sock, "Number must be from 1 to 10")
            return

        self.numbers[player_index] = number
        if len(self.numbers) < 2:
            self.send_packet(sock, "CONN_WAIT", {"match_id": 123456, "status": "waiting for number"})
            return

        first_player = self.choose_first_player()
        self.active_player = first_player
        self.state = "SHIP_PLACEMENT"
        self.broadcast("GAME_START", {
            "board_size": BOARD_SIZE,
            "active_player": first_player,
            "ships": [{"name": name, "length": length} for name, length in SHIPS],
            "message": "Place all ships",
        })

    def choose_first_player(self) -> int:
        distances = {
            index: abs(number - self.secret_number)
            for index, number in self.numbers.items()
        }
        lowest = min(distances.values())
        closest = [index for index, distance in distances.items() if distance == lowest]
        if len(closest) == 1:
            return closest[0]

        for packet_index in range(10):
            digests = {
                index: int(hashlib.sha256(
                    f"{index}:{self.numbers[index]}:{packet_index}".encode("utf-8")
                ).hexdigest()[-1], 16)
                for index in closest
            }
            largest = max(digests.values())
            finalists = [index for index, digest in digests.items() if digest == largest]
            if len(finalists) == 1:
                return finalists[0]
        return sorted(closest)[0]

    def handle_place_ship(self, sock: socket.socket, connection: Connection, contents: dict) -> None:
        if self.state != "SHIP_PLACEMENT":
            self.send_error(sock, "PLACE_SHIP is not valid now")
            return
        if connection.player_index is None:
            self.send_error(sock, "Player is not registered")
            return

        player_index = connection.player_index
        ship_name = contents.get("ship")
        coordinates = contents.get("coordinates")
        orientation = str(contents.get("orientation", "")).lower()

        ship_length = next((length for name, length in SHIPS if name == ship_name), None)
        if ship_length is None:
            self.send_error(sock, "Unknown ship name")
            return
        if ship_name in self.placed_ships[player_index]:
            self.send_error(sock, f"{ship_name} has already been placed")
            return
        if orientation not in ("horizontal", "vertical"):
            self.send_error(sock, "Orientation must be horizontal or vertical")
            return
        if not isinstance(coordinates, dict):
            self.send_error(sock, "Coordinates must contain row and col")
            return
        try:
            row = int(coordinates.get("row"))
            col = int(coordinates.get("col"))
        except (TypeError, ValueError):
            self.send_error(sock, "Coordinates must be integers")
            return

        occupied = set()
        for offset in range(ship_length):
            cell = (row + offset, col) if orientation == "vertical" else (row, col + offset)
            if not (0 <= cell[0] < BOARD_SIZE and 0 <= cell[1] < BOARD_SIZE):
                self.send_error(sock, "Ship is outside the board")
                return
            occupied.add(cell)

        existing = set().union(*self.boards[player_index].ships.values()) if self.boards[player_index].ships else set()
        if occupied & existing:
            self.send_error(sock, "Ship overlaps another ship")
            return

        self.boards[player_index].ships[ship_name] = occupied
        self.placed_ships[player_index].add(ship_name)
        self.send_packet(sock, "PLACE_ACCEPTED", {
            "ship": ship_name,
            "remaining": [
                name for name, _ in SHIPS
                if name not in self.placed_ships[player_index]
            ],
        })
        print(f"Player {player_index + 1} placed {ship_name}")

        if all(len(self.placed_ships[index]) == len(SHIPS) for index in (0, 1)):
            self.state = "PLAYING"
            self.broadcast("SHIPS_PLACED", {
                "board_size": BOARD_SIZE,
                "active_player": self.active_player,
            })

    def handle_player_turn(self, sock: socket.socket, connection: Connection, contents: dict) -> None:
        if self.state != "PLAYING":
            self.send_error(sock, "PLAYER_TURN is not valid now")
            return
        if connection.player_index is None:
            self.send_error(sock, "Player is not registered")
            return
        if connection.player_index != self.active_player:
            self.send_error(sock, "Not your turn")
            return

        coordinates = contents.get("coordinates", contents)
        if not isinstance(coordinates, dict):
            self.send_error(sock, "Coordinates must contain row and col")
            return
        try:
            row = int(coordinates.get("row"))
            col = int(coordinates.get("col"))
        except (TypeError, ValueError):
            self.send_error(sock, "Coordinates must be integers")
            return
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            self.send_error(sock, "Guess is outside the board")
            return

        shooter = connection.player_index
        target = 1 - shooter
        guess = (row, col)
        if guess in self.boards[target].guesses:
            self.send_error(sock, "Coordinate was already guessed")
            return

        self.boards[target].guesses.add(guess)
        hit = any(guess in cells for cells in self.boards[target].ships.values())
        sunk_ships = self.sunk_ship_names(target)
        all_sunk = all(
            all(cell in self.boards[target].guesses for cell in cells)
            for cells in self.boards[target].ships.values()
        ) and len(self.boards[target].ships) == len(SHIPS)

        if all_sunk:
            self.state = "GAME_OVER"
            self.broadcast("GAME_OVER", {
                "winner": shooter,
                "reason": "all ships sunk",
                "winner_hits": len(self.boards[target].guesses),
                "winner_misses": len(self.boards[target].guesses) - sum(
                    1 for cell in self.boards[target].guesses
                    if any(cell in cells for cells in self.boards[target].ships.values())
                ),
            })
            print(f"Player {shooter + 1} wins")
            self.reset_match(keep_connections=False)
            return

        self.active_player = target
        self.broadcast("TURN_RESULT", {
            "shooter": shooter,
            "coordinates": {"row": row, "col": col},
            "result": "hit" if hit else "miss",
            "sunk_ships": sunk_ships,
            "active_player": target,
        })
        print(f"Player {shooter + 1} guessed {chr(65 + row)}{col + 1}: {'hit' if hit else 'miss'}")

    def sunk_ship_names(self, player_index: int) -> list[str]:
        board = self.boards[player_index]
        return [
            name
            for name, cells in board.ships.items()
            if cells and all(cell in board.guesses for cell in cells)
        ]

    def run(self) -> None:
        try:
            while True:
                events = self.selector.select(timeout=1)
                for key, mask in events:
                    if key.data is None:
                        self.accept(key.fileobj)
                    else:
                        self.receive(key, mask)
        except KeyboardInterrupt:
            print("\nCaught keyboard interrupt, stopping server")
        finally:
            self.selector.close()
            if self.listening_socket is not None:
                self.listening_socket.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Two-player Battleship server")
    parser.add_argument("-p", "--port", type=int, required=True, help="TCP listening port")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    return args


def main() -> int:
    args = parse_args()
    server = GameServer(args.port)
    server.start()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
