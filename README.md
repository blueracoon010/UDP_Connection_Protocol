
# UDP-Client-Server-Chat

A UDP-based client-server chat system in Python using sockets, supporting dynamic client registration, peer-to-peer connection requests, reliable sequenced messaging, and connection termination.

---

## Setup and Usage

### Requirements

- Python 3.10.6 or 3.12.0  
- No external libraries required  

---

## Running the Server

Open a terminal window  
Navigate to the project directory  

Start the server:

The server will begin listening on **localhost:7070** using a UDP socket.

The server:

- Maintains a table of active clients and their port numbers  
- Displays updates whenever a client joins or leaves  
- Responds to client port lookup requests  

---

## Running the Client(s)

Open a new terminal window for each client  

Start a client:

Upon startup, the client:

- Creates a UDP socket  
- Sends its port number to the server at localhost:7070  
- Registers itself as active  
- Waits for connection requests or user commands  

Once connected to another client, you can begin typing messages.

---

## Available Commands

- `connect <client_id>` — Request connection to another active client  
- `accept` — Accept an incoming connection request  
- `reject` — Reject an incoming connection request  
- `send <message>` — Send a sequenced message to the connected client  
- `terminate` — Terminate the current connection  
- `leave` — Leave the application (notifies server and closes socket)  

---

## System Behavior

- The server automatically updates and prints the active client list upon any join or leave.  
- Clients request the UDP port of another client before attempting a direct connection.  
- Connection requests are retransmitted every 10 seconds until accepted or rejected.  
- Messages are sent with sequence numbers and require acknowledgment within 10 seconds.  
- Duplicate messages (same sequence number) are discarded.  
- Either client may terminate a connection.  
- Clients must send a `"Client Leave"` message before closing.

