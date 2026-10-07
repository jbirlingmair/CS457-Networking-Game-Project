# Transport Layer & Packet Framing Mechanism
- **Transport Protocol:** TCP
- **Serialization Format:** Structured JSON
- **Framing Rule Requirement:** Newline-Delimited JSON. Every JSON object is UTF-8 encoded and terminated by a newline character \n (0x0A). The receiver accumulates incoming bytes into a stream buffer until a \n is encountered, extracts the complete line, and deserializes the JSON object.

# Application Messages
| Message Type | Direction | Purpose & Description |
| --- | --- | --- |
| `CONNECT` | Client -> Server | Client requests to connect to server with match ID/password. |
| `CONN_WAIT` | Server -> Client | Server tells client that the server is waiting for the other player to connect. |
| `CONN_CONFIRM` | Server -> Client | Server tells client that the server has received another player, and that it needs a number between 1 and 10 to tell who goes first. |
| `PLAYER_NUMBER ` | Client -> Server | Client tells server which number the player guessed. |
| `GAME_START` | Server -> Client | The server informs the client of the initial game state and who goes first. |
| `PLACE_SHIP` | Client -> Server | The client tells the server the coordinates and orientation, and which ship, the player has placed. |
| `SHIPS_PLACED` | Server -> Client | The server tells the client that all ships for both players have been placed and the game will begin. |
| `PLAYER_TURN` | Client -> Server | The client tells the server which coordinate they are guessing to strike. |
| `TURN_RESULT` | Server -> Client | The server tells the client whether the previously guessed coordinate is a hit or a miss. |
| `ERROR` | Server -> Client | Server tells the client that there is an error, like bad guess, garbled message, or other error. |
| `DISCONNECT` | Client -> Server | The clients informs the server of an intentional disconnect. |
| `GAME_OVER` | Server -> Client | The server informs the client that the game is over, how many hits/misses they had, and who won. |

# Concrete Message Example
```json
{
  "packet_type": "CONNECT",
  "player_id": "AAAAFFFF",
  "contents": {
    "match_id": 123456,
  },
  "timestamp": 1800000000 
}
```
