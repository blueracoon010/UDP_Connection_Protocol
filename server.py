import socket
import threading

SERVER_PORT = 7070
BUFFER_SIZE = 1024

# Mapping of client_id : UDP port
# This is the entire "directory service" dataset
client_directory = {}

# Protects client_directory during concurrent read/write access
directory_lock = threading.Lock()


def print_client_directory():

    print("\n======= ACTIVE CLIENTS =======")
    if not client_directory:
        print("(none)")
    else:
        for cid, port in client_directory.items():
            print(f"Client {cid} → Port {port}")
    print("===============================\n")


def dispatch_requests(udp_socket):

    print(f"Server listening on UDP port {SERVER_PORT}...\n")

    while True:
        # recvfrom() gives us both the datagram and the origin endpoint.
        payload, sender_endpoint = udp_socket.recvfrom(BUFFER_SIZE)
        message = payload.decode()

        print(f"[SERVER] Received from {sender_endpoint}: {message}")

        # Each datagram conforms to a <TYPE>:<param>:<param>... format.
        fields = message.split(":")
        operation = fields[0]

       
        # REGISTER : Client announces its identity + listening port
        if operation == "REGISTER":
            client_id = fields[1]
            port = int(fields[2])

            # Thread-safe update of our directory
            with directory_lock:
                client_directory[client_id] = port
                print(f"[SERVER] Registered Client {client_id} on port {port}")
                print_client_directory()

            # ACK confirms the server has accepted and recorded the registration
            ack = f"REGISTERED:{client_id}"
            udp_socket.sendto(ack.encode(), sender_endpoint)
            print(f"[SERVER] ACK SENT TO {sender_endpoint}")

        # QUERY : Client asks for the port number of another client
        elif operation == "QUERY":
            requester = fields[1]
            target = fields[2]

            with directory_lock:
                if target in client_directory:
                    target_port = client_directory[target]
                    reply = f"PORT:{target}:{target_port}"
                else:
                    # Indicates that the target is not present in our directory
                    reply = f"INACTIVE:{target}"

            udp_socket.sendto(reply.encode(), sender_endpoint)
            print(f"[SERVER] Sent → {requester}: {reply}")

        # LEAVE : Client  exits the system
        elif operation == "LEAVE":
            client_id = fields[1]

            # Remove from directory if present
            with directory_lock:
                if client_id in client_directory:
                    del client_directory[client_id]
                    print(f"[SERVER] Client {client_id} left the system.")
                    print_client_directory()

            # Notify client that deregistration is complete
            ack = f"LEAVE_ACK:{client_id}"
            udp_socket.sendto(ack.encode(), sender_endpoint)


def start_server():

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(("localhost", SERVER_PORT))

    print("====  Server  has started ====")
    print(f"Listening on localhost:{SERVER_PORT}\n")

    listener = threading.Thread(
        target=dispatch_requests,
        args=(udp_socket,),
        daemon=True
    )
    listener.start()

    try:
        listener.join()
    except KeyboardInterrupt:
        print("\nServer is closed .")
        udp_socket.close()


if __name__ == "__main__":
    start_server()
