```flowchart TD
    A[Server starts] -->|Server started and listening| B(Waiting for players)
    B -->|CONNECT| C[Wait for other player]
    C -->|DISCONNECT| B
    C -->|CONN_CONFIRM| D[Wait for num]
    D -->|PLAYER_NUMBER| E[Server gets numbers]
    D -->|DISCONNECT| B
    E -->|GAME_START| F[Server waits for ship placements]
    E -->|DISCONNECT| B
    F -->|PLACE_SHIP| G[Board updated]
    G -->|PLACE_SHIP| G 
    G -->|SHIPS_PLACED| H[Wait for guesses]
    H -->|PLAYER_TURN| I[Hit or miss]
    I -->|TURN_RESULT| H
    H -->|GAME_OVER| J[Game is over]
    J --> B
    F -->|DISCONNECT| DIS[Disconnected]
    DIS -->|No re CONNECT| J
    G-->|DISCONNECT| DIS
    H-->|DISCONNECT| DIS
```
