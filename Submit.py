# CITS3002 2021 Assignment
#
# This file implements a basic server that allows a single client to play a
# single game with no other participants, and very little error checking.
#
# Any other clients that connect during this time will need to wait for the
# first client's game to complete.
#
# Your task will be to write a new server that adds all connected clients into
# a pool of players. When enough players are available (two or more), the server
# will create a game with a random sample of those players (no more than
# tiles.PLAYER_LIMIT players will be in any one game). Players will take turns
# in an order determined by the server, continuing until the game is finished
# (there are less than two players remaining). When the game is finished, if
# there are enough players available the server will start a new game with a
# new selection of clients.

import random
import socket
import threading
import time
from threading import Timer

import tiles
from tiles import BOARD_HEIGHT, BOARD_WIDTH

# 10 seconds timeout to handle idle client
TIMEOUT = 10

# Game pasue 5 seconds to restart (this time can be changes as requirement)
GAME_PASUE = 5

# Game will wait 10 seconds to start each round
GAME_START_TIME = 10


# Class game was designed to be responsible for automatically and randomly putting
# token and tiles on the board. And Class game also controls number of players in the game
# like(adding a person or remove a person). this class is also calling functions from tiles.py
# to send messages around the players 


class Game:
    def __init__(self):
        # All player instances including audience
        self.pool = []
        # Initialized with elements in pool with index 0 - 3
        self.gamer_list = []
        # Initialized with elements in pool with index 4 - last one
        self.audience_list = []
        # All the player idnums
        self.live_idnums = []
        # Eliminated players' idnum
        self.eliminated_player = []
        # Record each token and tile placement in each round
        self.game_record = []

        self.cur_id = -1
        # Initialized with Class board in tiles.py
        self.board = None

        self.running = False
        self.game_status = False
        self.is_first_round = True

    # Acquire all the tile positions on the board
    def get_all_place_tile(self, ):
        pos_list = []
        for i in range(BOARD_WIDTH):
            for j in range(BOARD_HEIGHT):
                pos = [i, j]
                pos_list.append(pos)
        return pos_list

    # Check if the current tile position is available
    # return all the available position for one idunm
    def get_player_available_tile(self, idnum):
        pos_list = self.get_all_place_tile()
        a_list = []
        for pos in pos_list:
            x = pos[0]
            y = pos[1]
            status = self.is_tile_available(x, y, idnum)
            if status:
                a_list.append(pos)
        return a_list

    # DuplicatedCode from tiles.py
    def is_tile_available(self, x: int, y: int, idnum: int):
        board = game.board

        if idnum in board.playerpositions:
            playerx, playery, _ = board.playerpositions[idnum]
            if x != playerx or y != playery:
                return False
        elif x != 0 and x != board.width - 1 and y != 0 and y != board.height - 1:
            return False

        idx = board.tile_index(x, y)

        if board.tileids[idx] != None:
            return False

        return True

    # Sent by sever to an idle client to randomly select a board position and
    # a random tile from a player's hand with random rotation
    # Rotation number 0, 1, 2, 3 as requirments
    def play_suggest_tile(self, idnum):
        # Find current person instance
        p = self.get_person_by_id(idnum)
        pos_list = self.get_player_available_tile(idnum)

        pos = random.choice(pos_list)
        x = pos[0]
        y = pos[1]

        tileid = random.choice(p.hands)
        rotation = random.choice([0, 1, 2, 3])

        msg = tiles.MessagePlaceTile(idnum, tileid, rotation, x, y)
        return msg

    # Sent by sever to an idle client to randomly choose a start token
    def play_suggest_token(self, idnum):
        # Get current person intance coresponding to the current player idnum
        p = self.get_person_by_id(idnum)
        pos_list = game.get_available_pos(p.start_x, p.start_y)
        position = random.choice(pos_list)

        msg = tiles.MessageMoveToken(idnum, p.start_x, p.start_y, position)
        return msg

    # There are eight tokens on one tile square
    # Two tokens on each edge
    def get_available_pos(self, x, y):
        nums = [0, 1, 2, 3, 4, 5, 6, 7]
        res = []
        for n in nums:
            status = self.is_vaild_pos(x, y, n)
            if status:
                res.append(n)
        return res

    # Choose token at start position and check if this token is valid
    def is_vaild_pos(self, x, y, position):
        if (position == 0 or position == 1) and y != BOARD_HEIGHT - 1:
            return False
        if (position == 2 or position == 3) and x != BOARD_WIDTH - 1:
            return False
        if (position == 4 or position == 5) and y != 0:
            return False
        if (position == 6 or position == 7) and x != 0:
            return False
        return True

    # To remove a quit user and it is called when there is a ConnectionResetError
    def remove_quit_user(self, idnum):
        old_p_list_length = len(self.pool)
        new_p_list = []

        # To aquire the rest of player idums apart from the quit one
        # This idnum can be belonged to a player or an audience
        for i in self.pool:
            if i.idnum != idnum:
                new_p_list.append(i)

        # To search in the gamer list
        new_gamer = []
        for i in self.gamer_list:
            if i.idnum != idnum:
                new_gamer.append(i)

        # Update the pool and gamer list
        self.pool = new_p_list
        self.gamer_list = new_gamer

        # If quit one is audience just return
        for i in self.audience_list:
            if i.idnum == idnum:
                return

        # If quit one is an eliminated player just return
        for i in self.eliminated_player:
            if i == idnum:
                return

        # Because these two are not equal, we need to inform others that a person has quit
        if old_p_list_length != len(new_p_list):
            self.send_msg_to_others(
                idnum, tiles.MessagePlayerEliminated(idnum).pack())

    # Remove a player instance by ID
    def remove_p_id(self, idnum, data):
        new_data = []
        for p in data:
            if p != idnum:
                new_data.append(p)
        return new_data

    # Remove a player(instance)
    def remove_p(self, idnum, data):
        new_data = []
        for p in data:
            if p.idnum != idnum:
                new_data.append(p)
        return new_data

    # Get rid of eliminated_players to update alive players
    def get_alive_player(self):
        alive_p = []
        for n in self.gamer_list:
            # Note: eliminated_player are storing idnums
            if n.idnum not in self.eliminated_player:
                alive_p.append(n.idnum)
        return alive_p

    def add_record(self, msg):
        self.game_record.append(msg)

    def send_record(self, idnum):
        for m in self.game_record:
            self.send_msg_by_id(idnum, m)

    # Add a new person(player or audience)
    def add_persons(self, connection, client_address):
        if self.game_status:
            # if it is in gaming, just add this new person as audience
            self.add_audience(connection, client_address)
        else:
            self.add_person(connection, client_address)

    def add_person(self, connection, client_address):
        self.cur_id += 1
        self.live_idnums.append(self.cur_id)

        p = Person(self.cur_id, connection, client_address)
        self.pool.append(p)

        idnum = self.cur_id
        self.send_msg_by_id(idnum, tiles.MessageWelcome(idnum).pack())
        self.send_msg_to_others(
            idnum, tiles.MessagePlayerJoined(p.name, p.idnum).pack())
        # res_p is a list containing all the other player's ids
        res_p = self.get_res_person(idnum)
        for r in res_p:
            # Search this player instance
            r_person = self.get_person_by_id(r)
            msg = tiles.MessagePlayerJoined(
                r_person.name, r_person.idnum).pack()
            Util.send_msg(idnum, connection, msg)

    def add_audience(self, connection, client_address):
        self.cur_id += 1
        self.live_idnums.append(self.cur_id)

        p = Person(self.cur_id, connection, client_address)
        self.pool.append(p)
        idnum = self.cur_id
        # We can only send a Welcome message but no PlayerJoined message
        self.send_msg_by_id(idnum, tiles.MessageWelcome(idnum).pack())
        # res_p is a list containning all the other player's idnums
        res_p = self.get_res_person(idnum)
        for r in res_p:
            # Search this player instance
            r_person = self.get_person_by_id(r)
            msg = tiles.MessagePlayerJoined(
                r_person.name, r_person.idnum).pack()
            Util.send_msg(idnum, connection, msg)
        self.send_record(idnum)  # Give this audience current board information

    # Get this person instance by id
    def get_person_by_id(self, id):
        for p in self.pool:
            if p.idnum == id:
                return p

    # Get rest of person corresponding to the input idnum
    def get_res_person(self, idnum):
        tmp = []
        for p in self.pool:
            if p.idnum != idnum:
                tmp.append(p.idnum)
        return tmp

    def send_msg_by_id(self, idnum, msg):
        for p in self.pool:
            p_id = p.idnum
            connection = p.connection
            if p_id == idnum:
                status = Util.send_msg(idnum, connection, msg)
                return status

    def send_msg_to_others(self, idnum, msg):
        for p in self.pool:
            p_id = p.idnum

            if p_id != idnum:
                connection = p.connection
                Util.send_msg(idnum, connection, msg)

    def send_msg_to_all(self, msg):
        for p in self.pool:
            connection = p.connection
            Util.send_msg(p.idnum, connection, msg)

    # Person will call update_tile() to update all the tile information for each player in pool
    def update_tile(self, msg):
        for p in self.pool:
            p.update_tile(msg)

    def is_start(self):
        return len(self.pool) >= 2

    # Notice all the player including each players themselves
    def notice_person_into_game(self):
        for p1 in self.pool:
            for p2 in self.pool:
                id1 = p1.idnum
                id2 = p2.idnum
                if id1 == id2:
                    self.send_msg_by_id(id1, tiles.MessageWelcome(id1).pack())
                else:
                    self.send_msg_by_id(
                        id1, tiles.MessagePlayerJoined(p2.name, p2.idnum).pack())

    def person_init(self):
        if not self.is_first_round:
            # After reset the game after the first round each person should call notice_person_into_game()
            self.notice_person_into_game()

        for p in self.pool:
            # Init their hand and tiles in their hands
            p.init_person()
            p.init_tile()

    def place_tile(self, index):
        for p in self.gamer_list:
            if p.idnum not in self.eliminated_player:
                game.send_msg_to_all(tiles.MessagePlayerTurn(p.idnum).pack())
                self.add_record(tiles.MessagePlayerTurn(p.idnum).pack())
                p.make_tile_turn(index)
            if self.is_end():
                self.game_status = False
                return

    def move_token(self):
        for p in self.gamer_list:
            if p.idnum not in self.eliminated_player:
                game.send_msg_to_all(tiles.MessagePlayerTurn(p.idnum).pack())
                self.add_record(tiles.MessagePlayerTurn(p.idnum).pack())
                p.make_move_token_turn()
            if self.is_end():
                self.game_status = False
                return

    # Decide weather this round has enough clients to open a game
    def is_end(self):
        self.eliminated_player = list(set(self.eliminated_player))
        cur_live = []
        for i in self.gamer_list:
            if i.idnum not in self.eliminated_player:
                cur_live.append(i)

        # There does not have enough clients to support one game
        if len(cur_live) <= 1:
            self.game_status = False
            print('game over')
            return True
        return False

    def person_take_turns(self):
        for i in range(1000):
            # First round to decide starting position
            if i == 0:
                self.place_tile(i)
            # To choose a token position at starting position
            elif i == 1:
                self.move_token()
            else:
                self.place_tile(i)

            if not self.game_status:
                self.is_first_round = False
                break

    def game_init(self):
        self.game_status = True
        self.eliminated_player = []
        self.board = tiles.Board()
        # self.game_record = []

    def set_gamer(self):
        random.shuffle(self.pool)
        self.gamer_list = self.pool[:tiles.PLAYER_LIMIT]
        self.audience_list = self.pool[tiles.PLAYER_LIMIT:]
        self.eliminated_player = []
        self.game_record = []

    def send_game_start(self):
        for p in self.pool:
            connection = p.connection
            Util.send_msg(p.idnum, connection, tiles.MessageGameStart().pack())

    def run_turn(self):
        for p in self.gamer_list:
            game.send_msg_to_all(tiles.MessagePlayerTurn(p.idnum).pack())

    # The main loop
    def run(self):
        while True:
            if self.is_start():
                self.game_init()
                self.set_gamer()
                self.send_game_start()
                self.person_init()
                self.run_turn()
                self.person_take_turns()

            time.sleep(GAME_PASUE)
            if len(self.pool) >= 2:
                self.run_turn()


# Class person was designed to be responsible for reading tiles and token movements from each client
# and resend the informantion back to each player
# Functions read_move_token_turn() and read_tile_turn() are crucial to handle idle clients and
# connections errors

class Person:
    def __init__(self, id, connection, client_address):
        self.idnum = id
        self.connection = connection
        self.address = client_address

        self.host, self.port = self.address
        self.name = '{}:{}'.format(self.host, self.port)
        self.hands = []
        self.start_x = None
        self.start_y = None

    def init_person(self):
        self.hands = []
        self.start_x = None
        self.start_y = None

    def add_tile(self, tileid):
        self.hands.append(tileid)

    def remove_tile(self, tileid):
        if tileid in self.hands:
            self.hands.remove(tileid)

    # Init tiles in a player's hand
    def init_tile(self):
        connection = self.connection
        for _ in range(tiles.HAND_SIZE):
            tileid = tiles.get_random_tileid()
            msg = tiles.MessageAddTileToHand(tileid).pack()
            self.add_tile(tileid)
            Util.send_msg(self.idnum, connection, msg)

    def make_tile_turn(self, index):
        msg = self.read_tile_turn()
        # If we could read the message from the client who is placing a tile
        if msg is not None:
            # Then we need to update this information about new placement of tile to all the others
            self.run_tile_turn(msg, index)

    # Reading the tile placement information
    def read_tile_turn(self):
        connection = self.connection
        address = self.address

        buffer = bytearray()
        try:
            while True:
                chunk = recv_data(connection)
                if not chunk:
                    print('client {} disconnected'.format(address))
                    return

                buffer.extend(chunk)

                while True:
                    msg, consumed = tiles.read_message_from_bytearray(buffer)
                    if not consumed:
                        break

                    buffer = buffer[consumed:]
                    if self.vaild_place_tile(msg):
                        return msg
        # Connection Loss
        except ConnectionResetError as e:
            return
        # Idle clients time out
        except Exception as e:
            if game.game_status:
                msg = game.play_suggest_tile(self.idnum)
                if self.vaild_place_tile(msg):
                    return msg

    def run_tile_turn(self, msg, index):
        connection = self.connection

        if isinstance(msg, tiles.MessagePlaceTile):
            # notify client that placement was successful
            game.add_record(msg.pack())
            # game.update_tile(msg) will go to class Game to call update_tile()
            # update_tile() in Game will go back to call update_tile() in Class person
            # Because pool[] is defined in the Class Game
            # Inform all the other clients that there is tile has been placed
            game.update_tile(msg)

            if index == 0:
                self.start_x = msg.x
                self.start_y = msg.y
            tileid = tiles.get_random_tileid()
            msg = tiles.MessageAddTileToHand(tileid).pack()
            # self.remove_tile(tileid)
            Util.send_msg(self.idnum, connection, msg)

    # Update tile information to all the clients once there is a new tile placement
    def update_tile(self, msg):
        board = game.board
        live_idnums = game.get_alive_player()
        idnum = self.idnum

        game.send_msg_to_all(msg.pack())
        positionupdates, eliminated = board.do_player_movement(live_idnums)

        for msg in positionupdates:
            # Update token information after this tile placed
            game.send_msg_to_all(msg.pack())

        if idnum in eliminated:
            # A player's token has reached the edge of board
            game.eliminated_player.append(idnum)
            game.send_msg_to_all(tiles.MessagePlayerEliminated(idnum).pack())
            return

    def run_move_token_turn(self, msg):
        if isinstance(msg, tiles.MessageMoveToken):
            # Record MoveToken Message for the audience
            game.add_record(msg.pack())
            self.update_move_token_turn()

    # Similar to update_tile()
    def update_move_token_turn(self):
        board = game.board
        live_idnums = game.get_alive_player()
        idnum = self.idnum

        positionupdates, eliminated = board.do_player_movement(live_idnums)

        for msg in positionupdates:
            game.send_msg_to_all(msg.pack())

        if idnum in eliminated:
            game.eliminated_player.append(idnum)
            game.send_msg_to_all(tiles.MessagePlayerEliminated(idnum).pack())
            return

    def vaild_place_tile(self, msg):
        if isinstance(msg, tiles.MessagePlaceTile):
            # set_tile()：If the tile cannot be placed, returns False, otherwise returns True.
            if game.board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
                return True
        return False

    def make_move_token_turn(self):
        msg = self.read_move_token_turn()
        if msg is not None:
            print('received message {}'.format(msg))
            self.run_move_token_turn(msg)

    def read_move_token_turn(self):
        try:
            connection = self.connection
            address = self.address

            buffer = bytearray()

            while True:
                chunk = recv_data(connection)
                if not chunk:
                    print('client {} disconnected'.format(address))
                    return

                buffer.extend(chunk)

                while True:
                    msg, consumed = tiles.read_message_from_bytearray(buffer)
                    if not consumed:
                        break

                    buffer = buffer[consumed:]
                    if self.vaild_move_token(msg):
                        return msg
        # connection lost
        except ConnectionResetError as e:
            return
        # idle clients time out
        except Exception as e:
            msg = game.play_suggest_token(self.idnum)
            if self.vaild_move_token(msg):
                return msg
            return

    def vaild_move_token(self, msg):
        board = game.board
        if isinstance(msg, tiles.MessageMoveToken):
            # Check if the given player (by idnum) has a token on the board
            if not board.have_player_position(msg.idnum):
                # Attempt to set the starting position for a player token
                if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
                    return True
        return False


class Util:
    @staticmethod
    def send_msg(idnum, connection, msg):
        try:
            connection.send(msg)
            return True
        # When sever tries to send a message but channel lost
        # which means the client has quit so a removement is neccessary here
        except Exception as e:
            game.remove_quit_user(idnum)
            print("The quit users is ", idnum)
            return False


def recv_data(connection):
    # If a non-zero value is given,
    # subsequent socket operations will raise a timeout exception if the timeout
    # period value has elapsed before the operation has completed
    # Two times(time1, time2) here are handling two messages arriving simultaneously
    """"There are two conditions due to the fact that even the client is not under his 
    or her turn, clicking on the board will still trigger a message being sent to the sever

    1. If recv() reads two packets of the same data 
    (client sends two packets of data at the same time), 
    it will only read the first one and then proceed to the next step

    2. If a client clicks board to place a tile not in her or his turn, the server will 
    receive this message and let us say this is msg1. After a small period, now it is this client's turn,
    the client places a tile and sends a message to the server and let us say this is msg2. 
    Condition here is that two messages were sent from the same client. Now recv1 will block itself, 
    because msg1 will be read at rev1. In following code, we will compare time1 and time2, 
    if time1 and time2 have very samll difference,it means that recv1 is reading the old message(msg1). 
    So we get rid of msg1 and let recv2 reads the new message.

    """

    time1 = time.time()
    connection.settimeout(TIMEOUT)
    chunk = connection.recv(4096)
    time2 = time.time()
    if time2 - time1 < 0.1:
        chunk = connection.recv(4096)
    return chunk


class ExtraThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        game.run()


def task():
    thread = ExtraThread()
    thread.start()


game = Game()

# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)

print('listening on {}'.format(sock.getsockname()))

sock.listen(5)

count_start = False
while True:
    # handle each new connection independently
    connection, client_address = sock.accept()
    print('received connection from {}'.format(client_address))
    # Creating player instance
    game.add_persons(connection, client_address)

    if not game.running and game.is_start():
        game.running = True
        # Wait GAME_START_TIME to start a new thread
        # Callback function
        Timer(GAME_START_TIME, task, ()).start()

