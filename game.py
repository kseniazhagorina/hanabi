#!usr/bin/env
# -*- coding: utf-8 -*-

import random
import subprocess
import traceback
import sys
import codecs
from datetime import datetime
from threading import Thread


COLORS = ['white', 'red', 'yellow', 'green', 'blue']
NOMINALS = {1:3, 2:2, 3:2, 4:2, 5:1}
COMMANDS = ['PLAY', 'FOLD', 'HINT']

INITIAL_HINTS = 8
MAX_ERRORS = 3

# Первое сообщение
# Количество_игроков(N) Мой_номер(0..N-1) Количество_подсказок(H) Количество_жизней(L) Количество_карт_в_руке(P)
# Номер игрока(0..N-1 кроме моего номера) карты в руке игрока(P шт): 
#    3 red 1 blue 2 green 3 yellow 4

# Каждое последующее сообщение
# Чей следующий ход(0..N-1)
#   TURN 3  (если это ваш номер то вы должны сделать ход иначе пропустить этот блок)
# Сделать ход:
#   PLAY ..x.
#   FOLD ..x.
#   HINT <player> x.x. color
#   HINT <player> x.x. nominal
# Ход игрока:
#   PLAY ..x. red 1
#   FOLD ..x. yellow 3
#   HINT <player> x.x. red
#   HINT <player> x.x. 2
# Полученная карта:
#   GET red 4
#   GET ? ? (если номер игрока - ваш собственный)
#   NONE (если игрок не получал новых карт)
# Количество_подсказок(H) количество_жизней(L)


class Player:
    def __init__(self, command):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True, bufsize=1, encoding='utf8')
        self.hand = []
    
    def empty_hand(self):
        return all(card is None for card in self.hand)
        
class Game:
    def __init__(self, config):
        players_binaries = codecs.open(config, 'r', 'utf-8').readlines()
        if len(players_binaries) < 2 or len(players_binaries) > 6:
            raise Exception('This game for 2-6 players, but found {}'.format(len(players_binaries)))
        self.players = [Player(bin) for bin in players_binaries]
        self.deck = [(color,nominal)
                     for color in COLORS
                     for nominal, count in NOMINALS.items()
                     for _ in range(count)]
        random.shuffle(self.deck) # колода
        self.discarded = [] # сброс
        self.played = dict([(color, 0) for color in COLORS]) # удачно сыгранные карты
        self.hints = INITIAL_HINTS
        self.lifes = MAX_ERRORS
        self.count_in_hand = 5 if len(self.players) <= 3 else 4
        for player in self.players:
            player.hand = [self.deck.pop() for _ in range(self.count_in_hand)]
        self.timeout_ms = 1000
        self.current_turn_player = random.choice(list(range(len(self.players))))
        self.log = codecs.open(datetime.now().strftime('%Y%m%d-%H%M%S')+'.log', 'w+', 'utf-8')
        self.exception = None

    def write_init_message(self):
       
        for player in range(len(self.players)):
            pinput = self.players[player].process.stdin
            pinput.write('{players} {player} {hints} {lifes} {in_hand}\n'.format(
                players=len(self.players), player=player, hints=self.hints, lifes=self.lifes, in_hand=self.count_in_hand))
        self.log.write('{players} {hints} {lifes} {in_hand}\n'.format(
                players=len(self.players), hints=self.hints, lifes=self.lifes, in_hand=self.count_in_hand))
            
        for p in range(len(self.players)):
            cards = ['{} {}'.format(color, nominal) for color, nominal in self.players[p].hand]
            player_hand = '{player} {cards}\n'.format(player=p, cards=' '.join(cards))
            self.log.write(player_hand)
            for player in range(len(self.players)):
                if p == player:
                    continue
                pinput = self.players[player].process.stdin
                pinput.write(player_hand)
                pinput.flush()

    def write_which_turn_message(self):
        for player in range(len(self.players)):
            pinput = self.players[player].process.stdin
            pinput.write('TURN {}\n'.format(self.current_turn_player))
            pinput.flush()
        self.log.write('TURN {}\n'.format(self.current_turn_player))

    def write_turn_message(self, turn):
        for player in range(len(self.players)):
            pinput = self.players[player].process.stdin
            pinput.write(turn+'\n')
            pinput.flush()
        self.log.write(turn+'\n')
        
    def write_get_card_message(self, card):
        get = 'NONE\n' if card is None else 'GET {} {}\n'.format(*card)
        get_curr =  'NONE\n' if card is None else 'GET ? ?\n'
        for player in range(len(self.players)):
            pinput = self.players[player].process.stdin
            pinput.write(get_curr if player == self.current_turn_player else get)
            pinput.flush()
        self.log.write(get)
            
    def write_status_message(self):
        status = '{hints} {lifes}\n'.format(hints=self.hints, lifes=self.lifes)
        for player in range(len(self.players)):
            pinput = self.players[player].process.stdin
            pinput.write(status)
            pinput.flush()
        self.log.write(status)
            
    def read_command(self):
        command = []
        def read_command():
            poutput = self.players[self.current_turn_player].process.stdout
            command.append(poutput.readline().strip())        
        
        t = Thread(target=read_command)
        t.start()
        t.join(float(self.timeout_ms)/1000)
        if t.is_alive():
            raise Exception('Player {} timed out'.format(self.current_turn_player))
        return command[0]
            
            
    def apply_command(self, command):
        parts = command.split()
        try:
            if len(parts) == 0:
                raise Exception('empty command')
            key = parts[0]            
            if key == 'PLAY' or key == 'FOLD':
                return self.apply_play_or_fold_command(key, parts)            
            elif key == 'HINT':
                return self.apply_hint_command(key, parts)
            else:
                raise Exception('invalid command keyword')
        except Exception as e:
            raise Exception('Player {} send invalid command [{}]: {}\n{}'.format(
                self.current_turn_player, command, e, traceback.format_exc()))

    def apply_play_or_fold_command(self, key, parts):             
        player = self.players[self.current_turn_player]
        if len(parts) != 2:
            raise Exception('too short of too long, expected [{} ..x.]'.format(key))
        code = parts[1]
        if len(code) != self.count_in_hand:
            raise Exception('expected {}-card position code'.format(code))
        selected = [i for i,x in enumerate(code) if x == 'x']
        if len(selected) != 1:
            raise Exception('expected only one card selected in {}'.format(code))
        position = selected[0]
        card = player.hand[position]
        if card is None:
            raise Exception('no card at position {}'.format(code))
        
        if key == 'FOLD':
            self.discarded.append(card)
            self.hints += 1
            
        else: # key == 'PLAY'
            color, nominal = card
            if self.played[color] != nominal - 1:
                self.discarded.append(card)
                self.lifes -= 1
            else:
                self.played[color] = nominal
                if nominal == 5:
                    self.hints += 1

        new_card = self.deck.pop() if self.deck else None
        player.hand[position] = new_card
        validated_command = '{} {} {} {}'.format(key, code, *card)
        return validated_command, new_card
        
    def apply_hint_command(self, key, parts):
        if len(parts) != 4:
            raise Exception('too short of too long, expected [HINT <player> <cards> color|nominal]')
        if self.hints == 0:
            raise Exception('you can not hint because there are no free hints')
        target_player_id = int(parts[1])
        if target_player_id < 0 or target_player_id >= len(self.players):
            raise Exception('expected player in [0..{}]'.format(len(self.players)-1))
        if target_player_id == self.current_turn_player:
            raise Exception('you can not hint to yourself')
        target_player = self.players[target_player_id]
        
        code = parts[2]
        if len(code) != self.count_in_hand:
            raise Exception('expected {}-card position code'.format(code))
        selected = [i for i,x in enumerate(code) if x == 'x']
        not_selected = [i for i,x in enumerate(code) if x != 'x']
        if len(selected) == 0:
            raise Exception('at least one card should be selected')
                            
        if any([target_player.hand[i] is None for i in selected]):
            raise Exception('no card at some of positions in hand of player {}'.format(code, target_player_id))
        hint = parts[3]
        if hint not in ['nominal', 'color']:
            raise Exception('invalid hint type {}, expected [color|nominal]'.format(hint))
        hint_id = 0 if hint == 'color' else 1
        hinted = list(set([target_player.hand[i][hint_id] for i in selected]))
        if len(hinted) != 1:
            raise Exception('not all cards at positions {} has the same {}'.format(code, hint))
        self.hints -= 1
        hinted = hinted[0]
        code = ''.join(['x' if target_player.hand[i] and target_player.hand[i][hint_id] == hinted else '.'
                        for i in range(self.count_in_hand)])
        validated_command = '{} {} {} {}'.format(key, target_player_id, code, hinted)
        return validated_command, None
    
    def check_game_over(self):
        if all([self.played[color] == 5 for color in COLORS]):
            return True # WIN
        if self.lifes < 0:
            return True # FAIL
        if all(player.empty_hand() for player in self.players):
            return True # ALL CARDS PLAYED
        return False
    
    def score(self):
        if self.exception is not None:
            return 0
        # сумма достоинств самых больших сыгранных карт
        return sum(self.played.values())
                
    def run(self):
        self.write_init_message() 
        while True:
            try:
                self.current_turn_player = (self.current_turn_player + 1) % len(self.players)
                if self.players[self.current_turn_player].empty_hand():
                    continue
                self.write_which_turn_message()
                command = self.read_command()
                turn, card = self.apply_command(command)
                self.write_turn_message(turn)
                self.write_get_card_message(card)
                self.write_status_message()
                if self.check_game_over():
                    self.log.write('SCORE {}\n'.format(self.score()))
                    print('SCORE {}\n'.format(self.score()))
                    break
                
            except Exception as e:
                self.exception = '{}\n{}'.format(e, traceback.format_exc())
                self.log.write('ERROR\n{}\n'.format(self.exception))
                print('ERROR {}\n'.format(self.exception))
                break
        self.log.flush()
        self.log.close()
        return self.score()
        
def main():
    config = sys.argv[1]
    game = Game(config)
    game.run()    

if __name__ == '__main__':
    main()