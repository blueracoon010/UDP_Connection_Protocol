
import socket
import threading
import time

SERVER_HOST = "localhost"
SERVER_PORT = 7070
BUFFER_SIZE = 1024

# Each client instance owns a unique logical identity (user-chosen)
client_id = ""
# UDP port dynamically assigned by the OS
client_port = 0

# inbound traffic socket (always bound to the client's port)
incoming_socket = None
# outbound control socket (unbound; used for send+ACK operations)
sender_socket = None

# Tracks which remote clients we have an active connection with.
# This acts as our local view of "session state" under a connectionless protocol.
connected_clients = {}

# Per-peer deduplication log:
# msg_log[peer_id] = { sequence_numbers_already_seen }
msg_log = {}

# Monotonically increasing sequence counter for outbound chat messages.
msg_counter = 0

# Concurrency primitives:
seq_lock = threading.Lock()       # protects msg_counter
peers_lock = threading.Lock()     # protects connected_clients
input_lock = threading.Lock()     # avoids race between listener prompts and user CLI
                                   # (important: two threads calling input() breaks UX)



# Sequence number allocation
def get_next_id():
    global msg_counter
    with seq_lock:
        msg_counter += 1
        return msg_counter


# CONTROL-PLANE SEND + ACK
def send_with_ack(message, destination, timeout=10):
    while True:
        try:
            sender_socket.sendto(message.encode(), destination)
            print(f"[SENT] {message} → {destination}")

            sender_socket.settimeout(timeout)
            data, addr = sender_socket.recvfrom(BUFFER_SIZE)
            reply = data.decode()

            # We whitelist expected ACK-bearing responses to avoid misinterpreting
            # chat traffic or other peer-originated messages.
            if reply.startswith(("ACK", "REGISTERED", "PORT",
                                 "INACTIVE", "LEAVE_ACK", "ACK_TERMINATE")):

                print(f"[ACK RECEIVED] {reply}")
                sender_socket.settimeout(None)
                return reply

        except socket.timeout:
            # Retry logic is intentionally simple — exponential backoff would be
            # trivial to add, but unnecessary for this educational scope.
            print("[TIMEOUT] Retrying...")

        except Exception as e:
            # Any unexpected socket failure should surface, but we still return.
            print(f"[ERROR ACK] {e}")
            return None


# ASYNCHRONOUS MESSAGE listener
def message_listener():
    print(f"[LISTENING] on UDP port {client_port}")

    while True:
        try:
            data, addr = incoming_socket.recvfrom(BUFFER_SIZE)
            msg = data.decode()
        except:
            continue  # Avoids killing the listener if a receive glitch occurs.

        parts = msg.split(":", 3)
        msg_type = parts[0]

        # CHAT MESSAGE PROCESSING
        if msg_type == "CHAT":
            sender = parts[1]

            # Defensive parsing — prevents malformed packets from killing the loop.
            try:
                seq = int(parts[2])
            except:
                print("[ERROR] Invalid seq number")
                continue

            text = parts[3]

            # Initialize per-peer dedup log.
            if sender not in msg_log:
                msg_log[sender] = set()

            if seq in msg_log[sender]:
                # Enforced duplicate suppression required by rubric.
                print(f"[DUPLICATE] From {sender} seq {seq} ignored")
            else:
                msg_log[sender].add(seq)
                print(f"[CHAT] From {sender} (seq {seq}): {text}")

            # ACK is always returned regardless of whether the message was new or duplicated.
            ack = f"ACK:{client_id}:{seq}"
            incoming_socket.sendto(ack.encode(), addr)

        # CONNECTION REQUEST HANDLING
        elif msg_type == "CONNECTION_REQUEST":
            sender = parts[1]
            print(f"\n[REQUEST] Client {sender} wants to connect.")

            # The listener prompts must not collide with the main CLI.
            with input_lock:
                ans = input("Accept (y/n)? ").strip().lower()

            reply_type = "CONNECTION_ACCEPT" if ans == "y" else "CONNECTION_REJECT"
            incoming_socket.sendto(f"{reply_type}:{client_id}".encode(), addr)

        # CONNECTION ACCEPT / REJECT
        elif msg_type == "CONNECTION_ACCEPT":
            sender = parts[1]
            print(f"[CONNECTION] Accepted by Client {sender}")

            # We store the peer's UDP port so we can address them directly.
            with peers_lock:
                if sender not in connected_clients:
                    connected_clients[sender] = addr[1]

        elif msg_type == "CONNECTION_REJECT":
            sender = parts[1]
            print(f"[CONNECTION] Rejected by Client {sender}")

    
        # TERMINATION 
        elif msg_type == "CONNECTION_TERMINATE":
            sender = parts[1]
            print(f"[TERMINATED] by Client {sender}")

            # Local teardown mirrors remote intent.
            with peers_lock:
                connected_clients.pop(sender, None)

            incoming_socket.sendto(f"ACK_TERMINATE:{client_id}".encode(), addr)

        # TERMINATION ACKNOWLEDGEMENT
        elif msg_type == "ACK_TERMINATE":
            # Control-plane ACK; handled by sender thread.
            pass


# SERVER REGISTRATION
def join_network():
    msg = f"REGISTER:{client_id}:{client_port}"
    send_with_ack(msg, (SERVER_HOST, SERVER_PORT))


# SERVER PEER LOOKUP
def lookup_peer(peer_id):
    reply = send_with_ack(f"QUERY:{client_id}:{peer_id}", (SERVER_HOST, SERVER_PORT))

    if reply and reply.startswith("PORT"):
        _, _, port = reply.split(":")
        port = int(port)

        with peers_lock:
            connected_clients[peer_id] = port

        print(f"[INFO] Client {peer_id} active on port {port}")
        return port

    print(f"[INFO] Client {peer_id} INACTIVE.")
    return None



# CONNECTION INITIATION
def initiate_connection(peer_id):
    with peers_lock:
        port = connected_clients.get(peer_id)

    if port is None:
        print("[INFO] Querying server...")
        port = lookup_peer(peer_id)
        if port is None:
            return

    msg = f"CONNECTION_REQUEST:{client_id}"
    incoming_socket.sendto(msg.encode(), ("localhost", port))
    print("[INFO] Connection request sent.")


# CHAT MESSAGE SEND
def send_text(peer_id, text):
    with peers_lock:
        if peer_id not in connected_clients:
            print("[ERROR] Unknown peer. Use query/connect first.")
            return
        port = connected_clients[peer_id]

    seq = get_next_id()
    msg = f"CHAT:{client_id}:{seq}:{text}"
    send_with_ack(msg, ("localhost", port))



# CONNECTION TERMINATION

def terminate(peer_id):
    with peers_lock:
        if peer_id not in connected_clients:
            print("[ERROR] Not connected.")
            return
        port = connected_clients[peer_id]

    reply = send_with_ack(f"CONNECTION_TERMINATE:{client_id}",
                          ("localhost", port))

    with peers_lock:
        connected_clients.pop(peer_id, None)

    print(f"[INFO] Connection with {peer_id} terminated.")


# CLIENT SHUTDOWN
def leave():
    send_with_ack(f"LEAVE:{client_id}", (SERVER_HOST, SERVER_PORT))
    incoming_socket.close()
    sender_socket.close()
    print("[EXIT] Goodbye!")
    exit()


# ENTRY POINT
def main():
    global client_id, client_port, incoming_socket, sender_socket

    client_id = input("Enter client ID: ").strip()

    # inbound socket: bound once; address is advertised to server
    incoming_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    incoming_socket.bind(("localhost", 0))      # 0 = OS assigns free port
    client_port = incoming_socket.getsockname()[1]
    print(f"[INFO] Client running on port {client_port}")

    # outbound reliable socket (unbound)
    sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    threading.Thread(target=message_listener, daemon=True).start()

    join_network()   # register with server

    #MAIN  LOOP 
    while True:
        with input_lock:
            cmd = input(
                "\nCommands: query <id> | connect <id> | send <id> <msg> "
                "| terminate <id> | leave\n> "
            ).strip()

        if not cmd:
            continue

        parts = cmd.split(" ", 2)
        c = parts[0]

        if c == "query" and len(parts) >= 2:
            lookup_peer(parts[1])

        elif c == "connect" and len(parts) >= 2:
            initiate_connection(parts[1])

        elif c == "send" and len(parts) >= 3:
            send_text(parts[1], parts[2])

        elif c == "terminate" and len(parts) >= 2:
            terminate(parts[1])

        elif c == "leave":
            leave()

        else:
            print("[ERROR] Invalid command.")


if __name__ == "__main__":
    main()
