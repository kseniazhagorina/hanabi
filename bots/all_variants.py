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

ALL_CARDS = [(color,nominal)
                             for color in COLORS
                             for nominal, count in NOMINALS.items()
                             for _ in range(count)]

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

class Possible(list):
        
    def discard(self, card):
        if card in self:
            self.remove(card)
    
    def discard_color(self, color, inverse=False):
        to_remove = [card for card in self if (card[0] == color) == (not inverse)]
        for card in to_remove:
            self.remove(card)

    def discard_nominal(self, nominal, inverse=False):
        to_remove = [card for card in self if (card[1] == nominal) == (not inverse)]
        for card in to_remove:
            self.remove(card)
            
    
class Player:
    def __init__(self, id, game):
        self.id = id
        self.game = game
        self.hand = []
        self.possible = Possible()

    
    def generate_possible(self, card_ind):
        '''Составить список возможных карт на позиции i
           Исключить оттуда карты которые уже сыграли, лежат в отбое или видны в руках других игроков'''
        
        self.possible[card_ind] = Possible()        
        if self.hand[card_ind] is None:
            return  
        
        possible = Possible(ALL_CARDS)
        # исключаются карты из отброса
        for card in self.game.discarded:
            possible.discard(card)
        # исключаются сыгранные карты
        for card in [(color, x) for color, count in self.game.played.items() for x in range(count)]:
            possible.discard(card)
        # исключаются карты других игроков
        for card in [card for player in self.game.players for card in player.hand if player.id != self.id]:
            possible.discard(card)   
        # исключаются известные карты в руке
        for i, possible_i in enumerate(self.possible):
            if i != card_ind and len(possible_i) == 1 and '?' not in self.hand[i]:
                possible.discard(self.hand[i])
        self.possible[card_ind] = possible

    def update_me_hand_and_other_possible(self):
        if self.id == self.game.me:
            while True: 
                updated = False
                for i, card in enumerate(self.hand):
                    if card is not None and '?' in card and len(self.possible[i]) == 1:
                        self.hand[i] = self.possible[i]
                        # обновляем свою руку
                        for j, possible in enumerate(self.possible):
                            if j != i:
                                self.possible[j].discard(self.hand[i])
                        # уточняем что знают другие игроки об их картах, когода видят мои карты
                        for other_possible in [p for player in self.game.players for p in player.possible if player.id != self.game.me]:
                            other_possible.discard(self.hand[i])
                        updated = True
                if not updated:
                    break
                    
            
    def make_turn(self):
        code = ['.']*len(self.hand)

        def try_play():
            for i, possible in enumerate(self.possible):
                if self.hand[i] is not None and all(self.game.played[card[0]] == card[1] - 1 for card in possible):
                    code[i] = 'x'
                    return 'PLAY {}'.format(''.join(code))
            return None
            
        def try_fold():
            for i, possible in enumerate(self.possible):
                if self.hand[i] is not None and all(self.game.played[card[0]] > card[1] - 1 for card in possible):
                    code[i] = 'x'
                    return 'FOLD {}'.format(''.join(code))

        def try_hint():
            # выбираем игрока которому выгодно подсказать
            max_score = 0
            max_hint = None
                
            for player in self.game.players:
                if player.id == self.game.me:
                    continue
                
                hints = set([card[0] for card in player.hand if card is not None] + [card[1] for card in player.hand if card is not None])
                for hint in hints:
                    selected = ([i for i, card in enumerate(player.hand) if card is not None and card[0] == hint] if hint in COLORS else
                                [i for i, card in enumerate(player.hand) if card is not None and card[1] == hint])
                    
                    score = self.game.try_hint(self.game.me, player.id, selected, hint)
                    if score > max_score:
                        max_score = score
                        max_hint = (player.id, selected, hint)
            
            if max_hint is not None:
                player_id, selected, hint = max_hint
                for i in selected:
                    code[i] = 'x'                
                return 'HINT {} {} {}'.format(player_id, ''.join(code), 'color' if hint in COLORS else 'nominal')
            return None
                
        def try_random_hint():
            players_ids = list(range(len(self.game.players)))
            random.shuffle(players_ids)
            for player_id in players_ids:
                if player_id == self.game.me:
                    continue
                not_none = [i for i,card in enumerate(self.game.players[player_id].hand) if card is not None]
                if len(not_none) == 0:
                    continue
                selected = random.choice(not_none)
                code[selected] = 'x'
                hint = random.choice(['color', 'nominal'])
                return 'HINT {} {} {}'.format(player_id, ''.join(code), hint)
            return None

        def try_random_fold():
            # случайный ход
            not_none = [i for i,card in enumerate(self.hand) if card is not None]
            selected = random.choice(not_none)
            code[selected] = 'x'
            return 'FOLD {}'.format(''.join(code))

        play = try_play()
        if play:
            sys.stderr.write('play\n')
            return play
        
        up_hints = try_fold() if self.game.hints < len(self.game.players)/2 else None
        if up_hints:
            sys.stderr.write('fold to up hints\n')
            return up_hints
            
        make_hint = try_hint() if self.game.hints > len(self.game.players) else None
        if make_hint:
            sys.stderr.write('make_hint\n')
            return make_hint
            
        fold = try_fold()
        if fold:
            sys.stderr.write('fold\n')
            return fold
            
        hint = try_hint() if self.game.hints > 0 else None
        if hint:
            sys.stderr.write('hint\n')
            return hint
            
        rand_hint = try_random_hint() if self.game.hints > 0 else None
        if rand_hint:
            sys.stderr.write('rand_hint\n')
            return rand_hint
            
        rand_fold = try_random_fold()
        if rand_fold:
            sys.stderr.write('rand_fold\n')
            return rand_fold
        
        
class Game:
    def __init__(self, n_players, me, hints, lifes, cards_in_hand, players_cards):

        self.hints = hints
        self.lifes = lifes
        self.me = me
        
        self.played = dict([(color, 0) for color in COLORS])
        self.discarded = []
        
        self.players = [Player(i, self) for i in range(n_players)]
        self.players[self.me].hand = [('?', '?') for _ in range(cards_in_hand)]
        self.players[self.me].possible = [Possible() for _ in range(cards_in_hand)]
        
        for player_id, hand in players_cards.items():
            self.players[player_id].hand = hand
            self.players[player_id].possible = [Possible() for _ in range(cards_in_hand)]
                
        for player in self.players:
            for i in range(cards_in_hand):
                player.generate_possible(i)
        
                
        
        
    def play_or_fold(self, player_id, card_id, card, new_card, played):
        color, nominal = card
        if played:
            sys.stderr.write('add to played color={} nominal={}'.format(color, nominal))
            self.played[color] = nominal
        else:
            self.discarded.append(card)
        
        self.players[player_id].hand[card_id] = new_card
        
        for player in self.players:
            for possible in player.possible:
                # сам игрок узнает о сыгранной карте, а другие узнают о новой карте
                possible.discard(new_card if player.id != player_id else card)
        
        self.players[player_id].generate_possible(card_id)
        self.players[self.me].update_me_hand_and_other_possible()
            
    def hint(self, player_from, player_to, selected, hint):
        if hint in COLORS:
            for i, possible in enumerate(self.players[player_to].possible):
                possible.discard_color(hint, inverse=i in selected)
        else:
            hint = int(hint)
            for i, possible in enumerate(self.players[player_to].possible):
                possible.discard_nominal(hint, inverse=i in selected)
        self.players[self.me].update_me_hand_and_other_possible()
    

    def try_hint(self, player_from, player_to, selected, hint):
        original = self.players[player_to].possible
        copy = [Possible(p) for p in self.players[player_to].possible]
        self.players[player_to].possible = copy
        self.hint(player_from, player_to, selected, hint)
        diff = sum(len(p) for p in original) - sum(len(p) for p in copy)
        self.players[player_to].possible = original
        return diff        
             
def main():

    n_players, me, hints, lifes, cards_in_hand = [int(x) for x in input().split()]
    players_cards = {}
    for _ in range(n_players - 1):
        line = input().split()
        player_id = int(line[0])
        players_cards[player_id] = []
        for i in range(cards_in_hand):
            players_cards[player_id].append((line[i*2 + 1], int(line[i*2 + 2])))
    
    game = Game(n_players, me, hints, lifes, cards_in_hand, players_cards)
    
    while True:
        try:
            which_turn = int(input().split()[1]) # TURN N
            if which_turn == game.me:
                print(game.players[game.me].make_turn())                        
            
            turn = input().split()
            get = input().split()
            game.hints, game.lifes = [int(x) for x in input().split()]
            if turn[0] == 'PLAY' or turn[0] == 'FOLD':
                code, color, nominal = turn[1], turn[2], int(turn[3])
                card = (color, nominal)
                card_id = code.index('x')
                new_card = None if get[0] == 'NONE' else ('?', '?') if which_turn == game.me else (get[1], int(get[2]))
                game.play_or_fold(which_turn, card_id, card, new_card,
                                  played = (turn[0] == 'PLAY' and game.played[color] == nominal - 1))
                game.players[game.me].update_me_hand_and_other_possible()
         
            if turn[0] == 'HINT':
                player_id, code, hint = int(turn[1]), turn[2], turn[3]
                selected = [i for i,x in enumerate(code) if x == 'x']
                game.hint(which_turn, player_id, selected, hint)
                game.players[game.me].update_me_hand_and_other_possible()
                
        except EOFError as e:
            exit(0)

if __name__ == '__main__':
    main()