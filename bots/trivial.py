#!usr/bin/env
# -*- coding: utf-8 -*-

import random
import subprocess
import traceback
import sys
from datetime import datetime


COLORS = ['white', 'red', 'yellow', 'green', 'blue']
NOMINALS = {1:3, 2:2, 3:2, 4:2, 5:1}
COMMANDS = ['PLAY', 'FOLD', 'HINT']

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
    def __init__(self):
        self.hand = []
        
def main():
    n_players, me, hints, lifes, cards_in_hand = [int(x) for x in input().split()]
    players = [Player() for _ in range(n_players)]
    players[me].hand = [('?', '?') for _ in range(cards_in_hand)]
    for _ in range(n_players - 1):
        line = input().split()
        player_id = int(line[0])
        for i in range(cards_in_hand):
            players[player_id].hand.append((line[i*2 + 1], int(line[i*2 + 2])))
            
    played = dict([(color, 0) for color in COLORS])
    discarded = []

    def make_turn():
        code = ['.']*cards_in_hand
        for i, card in enumerate(players[me].hand):
            if card is not None and card[0] != '?' and card[1] != '?' and played[card[0]] == card[1] - 1:
                code[i] = 'x'
                print('PLAY {}'.format(''.join(code)))
                return
        for i, card in enumerate(players[me].hand):
            if card is not None and ((card[0] != '?' and card[1] != '?' and played[card[0]] > card[1] - 1) or
                                     (card[1] != '?' and all(played_card > card[1] - 1 for played_card in played.values())) or
                                     (card[0] != '?' and played[card[0]] == 5)):
                code[i] = 'x'
                print('FOLD {}'.format(''.join(code)))
                return
        
        if hints > 0:
            players_ids = list(range(n_players))
            random.shuffle(players_ids)
            for player_id in players_ids:
                if player_id == me:
                    continue
                not_none = [i for i,card in enumerate(players[player_id].hand) if card is not None]
                if len(not_none) == 0:
                    continue
                selected = random.choice(not_none)
                code[selected] = 'x'
                hint = random.choice(['color', 'nominal'])
                print('HINT {} {} {}'.format(player_id, ''.join(code), hint))
                return
        
        not_none = [i for i,card in enumerate(players[me].hand) if card is not None]
        selected = random.choice(not_none)
        code[selected] = 'x'
        print('FOLD {}'.format(''.join(code)))
            
                        
            
    while True:
        try:
            which_turn = int(input().split()[1]) # TURN N
            if which_turn == me:
                make_turn()                        
            
            turn = input().split()
            get = input().split()
            hints, lifes = [int(x) for x in input().split()]
            if turn[0] == 'PLAY' or turn[0] == 'FOLD':
                code, color, nominal = turn[1], turn[2], int(turn[3])
                if turn[0] == 'PLAY' and played[color] == nominal - 1:
                    played[color] = nominal
                else:
                    discarded.append((color, nominal))
                card_id = code.index('x')
                card = None if get[0] == 'NONE' else ('?', '?') if which_turn == me else (get[1], int(get[2]))
                players[which_turn].hand[card_id] = card
                                
            if turn[0] == 'HINT':
                player_id, code, hint = int(turn[1]), turn[2], turn[3]
                if player_id == me:
                    selected = [i for i,x in enumerate(code) if x == 'x']
                    if hint in COLORS:
                        for i in selected:
                            players[me].hand[i] = (hint, players[me].hand[i][1])
                    else:
                        for i in selected:
                            players[me].hand[i] = (players[me].hand[i][0], int(hint))
        except EOFError as e:
            exit(0)

if __name__ == '__main__':
    main()