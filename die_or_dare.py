import abc
import argparse
import collections
import constants
import datetime
import functools
import itertools
import json
import jsonpickle
import keyboard
import numpy
import os
import random
import time


class Input(abc.ABC):
    @staticmethod
    def validate(function_):
        @functools.wraps(function_)
        def wrapper_validate(*args, **kwargs):
            if args[0].is_valid():
                return function_(*args, **kwargs)
            else:
                raise ValueError('Invalid input.')

        return wrapper_validate

    @abc.abstractmethod
    def is_valid(self, *args, **kwargs):
        pass

    @property
    @abc.abstractmethod
    def value(self):
        pass


class NameInput(Input):
    def __init__(self, name=None):
        self._name = name

    def is_valid(self):
        if self._name is None:
            return False
        return self._name.isalnum()

    @property
    def value(self):
        return self._name


class NameTextInput(NameInput):
    @classmethod
    def from_human(cls, prompt, forbidden_name=None):
        name = input(prompt)
        while not name.isalnum() or name == forbidden_name:
            if name == forbidden_name:
                error_message = "You can't use that name. Choose another name."
            else:
                error_message = 'Only alphanumeric characters are allowed.'
            name = input(error_message + '\n' + prompt)
        return cls(name)

    @classmethod
    def auto_generate(cls, forbidden_name):
        name = 'Computer' + str(random.randint(1, 999999))
        if name == forbidden_name:
            name += 'a'
        return cls(name)


class KeySettingsInput(Input):
    def __init__(self, key_settings=None):
        self._key_settings = key_settings

    def is_valid(self):
        if self._key_settings is None:
            return False
        all_actions_set = all(
            self._key_settings.get(action) is not None for action in
            constants.Action)
        num_keys = len(set(self._key_settings.keys()))
        num_values = len(set(self._key_settings.values()))
        all_keys_distinct = num_keys == num_values
        return all_actions_set and all_keys_distinct

    @property
    def value(self):
        return self._key_settings

    @staticmethod
    def bottom_left():
        return {constants.Action.IDLE: 'b', constants.Action.DARE: 'z',
                constants.Action.DIE: 'x',
                constants.Action.DONE: 'c', constants.Action.DRAW: 'v'}

    @staticmethod
    def top_left():
        return {constants.Action.IDLE: 't', constants.Action.DARE: 'q',
                constants.Action.DIE: 'w',
                constants.Action.DONE: 'e', constants.Action.DRAW: 'r'}

    @staticmethod
    def top_right():
        return {constants.Action.IDLE: 'y', constants.Action.DARE: 'u',
                constants.Action.DIE: 'i',
                constants.Action.DONE: 'o', constants.Action.DRAW: 'p'}


class KeySettingsTextInput(KeySettingsInput):
    @classmethod
    def from_human(cls, player_name, blacklist=None):
        key_settings = {action: '' for action in constants.Action}
        if blacklist is None:
            blacklist = []
        for action in key_settings:
            prompt = '{}, which key will you use to indicate {}? '.format(
                player_name, action.name)
            key = input(prompt)
            is_single = len(key) == 1
            is_lower = key.islower()
            is_not_duplicate = key not in blacklist
            is_valid_key = is_single and is_lower and is_not_duplicate
            while not is_valid_key:
                if key in blacklist:
                    error_message = "You can't use the following key(s): {}".format(
                        ', '.join(blacklist))
                else:
                    error_message = 'Use a single lowercase alphabet.'
                prompt = '{}, which key will you use to indicate {}? '.format(
                    player_name, action.name)
                key = input(error_message + '\n' + prompt)
                is_single = len(key) == 1
                is_lower = key.islower()
                is_not_duplicate = key not in blacklist
                is_valid_key = is_single and is_lower and is_not_duplicate
            key_settings[action] = key
            blacklist.append(key)
        return cls(key_settings)


class JokerValueStrategy(abc.ABC):
    @staticmethod
    @abc.abstractmethod
    def apply(cards):
        pass


class Thirteen(JokerValueStrategy):
    @staticmethod
    def apply(cards):
        """Assign 13."""
        for card in cards:
            if card._is_joker():
                card._value = max(rank.value for rank in constants.Rank)
                break


class SameAsMax(JokerValueStrategy):
    @staticmethod
    def apply(cards):
        """Assign the biggest value that is already in the deck."""
        if any(card._is_joker() for card in cards):
            joker = next(card for card in cards if card._is_joker())
            cards_without_joker = [card for card in cards if card != joker]
            biggest = max(cards_without_joker, key=lambda x: x._value)
            joker._value = biggest._value


class RandomNumber(JokerValueStrategy):
    @staticmethod
    def apply(cards):
        """Assign a random number."""
        for card in cards:
            if card._is_joker():
                values = [rank.value for rank in constants.Rank]
                card._value = random.choice(values)
                break


class NextBiggest(JokerValueStrategy):
    @staticmethod
    def apply(cards):
        """Assign the next biggest value that is not yet in the deck."""
        if any(card._is_joker() for card in cards):
            joker = next(card for card in cards if card._is_joker())
            cards_without_joker = [card for card in cards if card != joker]
            biggest = max(cards_without_joker, key=lambda x: x._value)
            smallest = min(cards_without_joker, key=lambda x: x._value)
            if biggest._value == 1:
                joker._value = 1
            elif biggest._value == 2:
                joker._value = 3 - smallest._value
            else:
                if smallest._value == biggest._value - 1:
                    joker._value = biggest._value - 2
                else:
                    joker._value = biggest._value - 1


class JokerPositionStrategy(abc.ABC):
    @staticmethod
    def biggest(cards):
        """Return the card with the biggest value"""
        return max(cards, key=lambda x: x._value)  # may or may not be a joker

    @staticmethod
    def to_delegate(cards, index):
        cards[0], cards[index] = cards[index], cards[0]

    @classmethod
    def biggest_to_delegate(cls, cards):
        biggest = cls.biggest(cards)
        biggest_index = cards.index(biggest)
        cls.to_delegate(cards, biggest_index)

    @classmethod
    @abc.abstractmethod
    def apply(cls, cards):
        pass


class JokerFirst(JokerPositionStrategy):
    @classmethod
    def apply(cls, cards):
        """Reveal the joker as soon as possible."""
        joker_index = -1
        for i in range(len(cards)):
            card = cards[i]
            if card._is_joker():
                joker_index = i
        if joker_index > -1:
            joker = cards[joker_index]
            cards_without_joker = [card for card in cards if
                                   not card._is_joker()]
            bigger = cls.biggest(cards_without_joker)
            bigger_index = cards.index(bigger)
            if joker._value >= bigger._value:
                cls.to_delegate(cards, joker_index)
            else:
                cls.to_delegate(cards, bigger_index)
        else:
            cls.biggest_to_delegate(cards)


class JokerLast(JokerPositionStrategy):
    @classmethod
    def apply(cls, cards):
        """Hide the joker as long as possible."""
        joker_index = -1
        for i in range(len(cards)):
            if cards[i]._is_joker():
                joker_index = i
        if joker_index > -1:
            joker = cards[joker_index]
            cards_without_joker = [card for card in cards if
                                   not card._is_joker()]
            bigger = cls.biggest(cards_without_joker)
            if joker._value > bigger._value:
                cls.to_delegate(cards, joker_index)
            else:
                bigger_index = cards.index(bigger)
                cls.to_delegate(cards, bigger_index)
                cards[-1], cards[joker_index] = cards[joker_index], cards[-1]
        else:
            cls.biggest_to_delegate(cards)


class JokerAnywhere(JokerPositionStrategy):
    @classmethod
    def apply(cls, cards):
        """Put the joker anywhere within the deck."""
        cls.biggest_to_delegate(cards)


class JokerNotFirst(JokerPositionStrategy):
    @classmethod
    def apply(cls, cards):
        """Put the joker anywhere but in the first position."""
        joker_index = -1
        for i in range(len(cards)):
            card = cards[i]
            if card._is_joker():
                joker_index = i
        if joker_index > -1:
            joker = cards[joker_index]
            cards_without_joker = [card for card in cards if card != joker]
            bigger = cls.biggest(cards_without_joker)
            if joker._value > bigger._value:
                cls.to_delegate(cards, joker_index)
            else:
                bigger_index = cards.index(bigger)
                cls.to_delegate(cards, bigger_index)
        else:
            cls.biggest_to_delegate(cards)


class JokerValueStrategyInput(Input):
    def __init__(self, strategy=None):
        self._strategy = strategy

    def is_valid(self):
        if self._strategy is None:
            return False
        is_subclass = issubclass(self._strategy, JokerValueStrategy)
        is_abstract = issubclass(JokerValueStrategy, self._strategy)
        return is_subclass and not is_abstract

    @property
    def value(self):
        return self._strategy


class JokerValueStrategyTextInput(JokerValueStrategyInput):
    @classmethod
    def from_human(cls, player_name):
        number_to_strategy = {1: Thirteen, 2: SameAsMax, 3: RandomNumber,
                              4: NextBiggest}
        valid_input = False
        input_value = None
        error_message = ''
        prompt = '\n{}, what value would you assign to your joker?'.format(
            player_name)
        prompt += ''.join('\n{}: {}'.format(number, strategy.apply.__doc__) for
                          number, strategy in number_to_strategy.items())
        prompt += '\nEnter a corresponding number: '
        while not valid_input:
            input_value = input(error_message + '\n' + prompt)
            try:
                input_value = int(input_value)
                if input_value not in number_to_strategy:
                    raise ValueError('Input not among choices.')
            except ValueError:
                numbers = (str(number) for number in number_to_strategy)
                numbers_concatenated = ', '.join(numbers)
                error_message = 'Enter a number among {}.'.format(
                    numbers_concatenated)
            else:
                valid_input = True
        strategy = number_to_strategy.get(input_value)
        return cls(strategy)


class JokerPositionStrategyInput(Input):
    def __init__(self, strategy=None):
        self._strategy = strategy

    def is_valid(self):
        if self._strategy is None:
            return False
        is_subclass = issubclass(self._strategy, JokerPositionStrategy)
        is_abstract = issubclass(JokerPositionStrategy, self._strategy)
        return is_subclass and not is_abstract

    @property
    def value(self):
        return self._strategy


class JokerPositionStrategyTextInput(JokerPositionStrategyInput):
    @classmethod
    def from_human(cls, player_name):
        number_to_strategy = {1: JokerFirst, 2: JokerLast, 3: JokerAnywhere,
                              4: JokerNotFirst}
        valid_input = False
        input_value = None
        error_message = ''
        prompt = '\n{}, where in the deck would you put the joker?'.format(
            player_name)
        prompt += ''.join('\n{}: {}'.format(number, strategy.apply.__doc__) for
                          number, strategy in number_to_strategy.items())
        prompt += '\nEnter a corresponding number: '
        while not valid_input:
            input_value = input(error_message + prompt)
            try:
                input_value = int(input_value)
                if input_value not in number_to_strategy:
                    raise ValueError('Input not among choices.')
            except ValueError:
                numbers = (str(number) for number in number_to_strategy)
                choices_str = ', '.join(numbers)
                error_message = 'Enter a number among {}.\n'.format(choices_str)
            else:
                valid_input = True
        strategy = number_to_strategy.get(input_value)
        return cls(strategy)


class OffenseDeckChoiceStrategy(abc.ABC):
    @staticmethod
    @abc.abstractmethod
    def apply(decks_me, decks_opponent, points_me, num_shout_die_me,
              points_opponent, num_shout_die_opponent):
        pass


class BiggestOffenseDeck(OffenseDeckChoiceStrategy):
    @staticmethod
    def apply(decks_me, decks_opponent=None, points_me=None,
              num_shout_die_me=None, points_opponent=None,
              num_shout_die_opponent=None):
        undisclosed_decks_me = [deck for deck in decks_me if
                                deck.is_undisclosed()]
        return max(undisclosed_decks_me, key=lambda x: x.index)


class AnyOffenseDeck(OffenseDeckChoiceStrategy):
    @staticmethod
    def apply(decks_me, decks_opponent=None, points_me=None,
              num_shout_die_me=None, points_opponent=None,
              num_shout_die_opponent=None):
        undisclosed_decks = [deck for deck in decks_me if deck.is_undisclosed()]
        return random.choice(undisclosed_decks)


class DefenseDeckChoiceStrategy(abc.ABC):
    @staticmethod
    @abc.abstractmethod
    def apply(decks_opponent, decks_me, points_me, num_shout_die_me,
              points_opponent, num_shout_die_opponent):
        pass


class SmallestDefenseDeck(DefenseDeckChoiceStrategy):
    @staticmethod
    def apply(decks_opponent, decks_me=None, points_me=None,
              num_shout_die_me=None, points_opponent=None,
              num_shout_die_opponent=None):
        undisclosed_decks_opponent = [deck for deck in decks_opponent if
                                      deck.is_undisclosed()]
        return min(undisclosed_decks_opponent, key=lambda x: x.index)


class AnyDefenseDeck(DefenseDeckChoiceStrategy):
    @staticmethod
    def apply(decks_opponent, decks_me=None, points_me=None,
              num_shout_die_me=None, points_opponent=None,
              num_shout_die_opponent=None):
        undisclosed_decks = [deck for deck in decks_opponent if
                             deck.is_undisclosed()]
        return random.choice(undisclosed_decks)


class StatsConsideredBiggest(DefenseDeckChoiceStrategy):
    @staticmethod
    def apply(decks_opponent, decks_me=None, points_me=None,
              num_shout_die_me=None, points_opponent=None,
              num_shout_die_opponent=None):
        undisclosed_decks = [deck for deck in decks_opponent if
                             deck.is_undisclosed()]
        remaining_die_opponent = constants.MAX_DIE - num_shout_die_opponent
        remaining_points_me = constants.REQUIRED_POINTS - points_me
        index = remaining_die_opponent + remaining_points_me - 1
        return undisclosed_decks[index]


class ActionChoiceStrategy(abc.ABC):
    @staticmethod
    @abc.abstractmethod
    def apply(round_, in_turn, decks_me, decks_opponent, num_shout_die_me,
              is_opponent_red, num_shout_die_opponent, points_me,
              points_opponent):
        pass


class SimpleActionChoiceStrategy(ActionChoiceStrategy):
    @staticmethod
    def apply(round_, in_turn, decks_me, decks_opponent, num_shout_die_me,
              is_opponent_red, num_shout_die_opponent=None, points_me=None,
              points_opponent=None):
        if not ComputerPlayer.undisclosed_values(decks_me):
            return constants.Action.DONE
        elif round_ in (1, 2):
            odds_win, odds_draw, odds_lose = ComputerPlayer.get_chances(
                decks_me, decks_opponent, is_opponent_red)
            if in_turn:
                odds_lose += odds_draw
            else:
                odds_win += odds_draw
            if num_shout_die_me < constants.MAX_DIE:
                if odds_lose > odds_win + .1:
                    if random.random() < .7:
                        return constants.Action.DIE
            return constants.Action.DARE
        elif round_ == 3:
            deck_in_duel_me = next(
                (deck for deck in decks_me if deck.is_in_duel()))
            deck_in_duel_opponent = next(
                (deck for deck in decks_opponent if deck.is_in_duel()))
            sum_me = sum(card._value for card in deck_in_duel_me)
            sum_opponent = sum(card._value for card in deck_in_duel_opponent)
            if sum_me == sum_opponent:
                return constants.Action.DRAW
            else:
                return None
        else:
            raise Exception('Something went wrong.')


class DeckInput(Input):
    def __init__(self, deck=None):
        self._deck = deck

    def is_valid(self):
        return isinstance(self._deck, Deck)

    @property
    def value(self):
        return self._deck


class DeckTextInput(DeckInput):
    @classmethod
    def from_human(cls, player_name=None, is_opponent=None,
                   undisclosed_decks=None):
        user_input_to_deck = {deck.index: deck for deck in undisclosed_decks}
        valid_input = False
        input_value = None
        possessive = "your opponent's" if is_opponent else 'your'
        prompt = '{}, choose one of {} decks. (Enter the deck number): '.format(
            player_name, possessive)
        while not valid_input:
            input_value = input(constants.INDENT + prompt)
            try:
                input_value = int(input_value) - 1
                if input_value not in user_input_to_deck:
                    raise ValueError('Input not among choices.')
            except ValueError:
                choices_generator = (str(deck.index + 1) for deck in
                                     undisclosed_decks)
                choices_str = ', '.join(choices_generator)
                error_message = 'Enter a number among {}.\n'.format(choices_str)
                prompt = error_message + prompt
            else:
                valid_input = True
        deck = user_input_to_deck.get(input_value)
        return cls(deck)


class DeckIndexInput(Input):
    def __init__(self, deck_index):
        self._deck_index = deck_index

    def is_valid(self, *args, **kwargs):
        return self._deck_index in range(constants.DECK_PER_PILE)

    @property
    def value(self):
        return self._deck_index


class OffenseDeckIndexInput(DeckIndexInput):
    pass


class DefenseDeckIndexInput(DeckIndexInput):
    pass


class Shout(object):
    def __init__(self, player, action):
        self._player = player
        self._action = action

    @property
    def player(self):
        return self._player

    @property
    def action(self):
        return self._action


class ShoutInput(Input):
    def __init__(self, shouts):
        self._shouts = shouts

    def is_valid(self, *args, **kwargs):
        try:
            iter(self._shouts)
        except TypeError:
            return False
        else:
            return all(isinstance(shout, Shout) for shout in self._shouts)

    @property
    def value(self):
        return self._shouts


class ShoutKeypressInput(ShoutInput):
    def __init__(self, keys_pressed):
        super().__init__(keys_pressed)
        self._keys_pressed = keys_pressed

    @classmethod
    def from_human(cls, keys_to_hook=None, timeout=0):
        def when_key_pressed(x):
            keyboard.unhook_key(x.name)
            keys_pressed.append(x.name)

        keys_pressed = []
        if keys_to_hook is None:
            keys_to_hook = []
        else:
            keys_to_hook = (key for key in keys_to_hook if key is not None)
        for key in keys_to_hook:
            keyboard.on_press_key(key, when_key_pressed)
        over = False
        start = time.time()
        while not over:
            over = time.time() - start > timeout
        keyboard.unhook_all()
        keys_str = ''.join(keys_pressed)
        return cls(keys_str)

    @property
    def value(self):
        return self._keys_pressed


class PlayerOrder(abc.ABC):
    def __init__(self, player1, player2):
        self._player1 = player1
        self._player2 = player2
        self._first = None
        self._second = None

    @property
    def players(self):
        return self._first, self._second


class RandomPlayerOrder(PlayerOrder):
    def __init__(self, player1, player2):
        super().__init__(player1, player2)
        if random.random() > .5:
            self._first = self._player1
            self._second = self._player2
        else:
            self._first = self._player2
            self._second = self._player1


class KeepOrder(PlayerOrder):
    def __init__(self, player1, player2):
        super().__init__(player1, player2)
        self._first = self._player1
        self._second = self._player2


class ReverseOrder(PlayerOrder):
    def __init__(self, player1, player2):
        super().__init__(player1, player2)
        self._first = self._player2
        self._second = self._player1


class Game(object):
    def __init__(self, player_red=None, player_black=None, over=False,
                 time_started=None, time_ended=None, winner=None, loser=None,
                 result=None, duels=None, *args):
        self.player_red = player_red  # takes the red pile and gets to go first
        self.player_black = player_black
        self._over = over
        if time_started is None:
            time_started = time.time()
        self.time_started = time_started
        self.time_ended = time_ended
        self.winner = winner
        self.loser = loser
        self.result = result
        self.duel_index = -1  # zero based
        if duels is None:
            duels = []
            for i in range(constants.DECK_PER_PILE):
                new_duel = Duel(player_red, player_black, i)
                duels.append(new_duel)
            self.duels = tuple(duels)
        self.duel_ongoing = None
        self.red_pile = RedPile().cards
        self.black_pile = BlackPile().cards

    @property
    def players(self):
        return self.player_red, self.player_black

    def build_decks(self):
        for player in self.players:
            player.build_decks()

    def _open_next_cards(self):
        for player in self.players:
            player.open_next_card()

    def to_next_duel(self):
        self.duel_index += 1
        self.duel_ongoing = self.duels[self.duel_index]
        self.duel_ongoing.start()
        for player in self.players:
            player.recent_action = None
        return self.duel_ongoing

    def is_over(self):
        return self._over

    def prepare(self):
        duel = self.duel_ongoing
        action_prompt = 'What will you two do?\nEnter your action!'
        if duel.offense.deck_in_duel is None:
            message = 'Duel #{} started! Time to choose the offense deck.'.format(
                duel.index + 1)
            duration = constants.Duration.BEFORE_DECK_CHOICE
        elif duel.defense.deck_in_duel is None:
            message = 'Time to choose the defense deck.'
            duration = constants.Duration.BEFORE_DECK_CHOICE
        elif duel.round_ in (1, 2):
            self._open_next_cards()
            duel.to_next_round()
            message = action_prompt
            duration = constants.Duration.BEFORE_ACTION
        else:
            message = 'Something went wrong.'
            duration = None
        return message, duration

    def accept(self, prev_envstate=None):
        # TODO: prev_envstate...
        duel = self.duel_ongoing
        if duel.offense.deck_in_duel is None:
            return self._decide_offense_deck(prev_envstate)
        elif duel.defense.deck_in_duel is None:
            return self._decide_defense_deck(prev_envstate)
        elif duel.round_ in (1, 2):
            timeout = constants.Duration.ACTION
            return self._get_actions(timeout=timeout,
                                     prev_envstate=prev_envstate)
        elif duel.round_ == 3:
            timeout = constants.Duration.FINAL_ACTION
            return self._get_actions(timeout=timeout,
                                     prev_envstate=prev_envstate)
        else:
            raise ValueError('Invalid.')

    def _get_actions(self, timeout=0, prev_envstate=None):
        duel = self.duel_ongoing
        round_ = duel.round_
        if all(isinstance(player, HumanPlayer) for player in self.players):
            keys = []
            for player in self.players:
                valid_actions = player.valid_actions(round_)
                for action in valid_actions:
                    key = player.key_settings.get(action)
                    keys.append(key)
            shout_input = ShoutKeypressInput.from_human(keys, timeout)
            return shout_input
        else:
            shouts = []
            for player in duel.players:
                in_turn = player == duel.offense
                opponent = duel.defense if in_turn else duel.offense
                shout = player.shout(opponent.decks, opponent.points,
                                     opponent.num_shout_die, round_, in_turn,
                                     duel.index, prev_envstate)
                action = shout.action
                shout = Shout(player, action)
                shouts.append(shout)
            shout_input = ShoutInput(shouts)
            return shout_input

    def process(self, intra_duel_input):
        if isinstance(intra_duel_input, OffenseDeckIndexInput):
            return self.process_offense_deck_index_input(intra_duel_input)
        elif isinstance(intra_duel_input, DefenseDeckIndexInput):
            return self.process_defense_deck_index_input(intra_duel_input)
        elif isinstance(intra_duel_input, ShoutKeypressInput):
            return self.process_shout_keypress(intra_duel_input)
        elif isinstance(intra_duel_input, ShoutInput):
            return self.process_shout(intra_duel_input)
        else:
            raise ValueError('Invalid input')

    def process_shout_keypress(self, intra_duel_input):
        duel = self.duel_ongoing
        round_ = duel.round_
        # See who did which action
        shouts = []
        keys_pressed = intra_duel_input.value
        for key_pressed in keys_pressed:
            for player in self.players:
                valid_actions = player.valid_actions(round_)
                key_to_action = {key: action for action, key in
                                 player.key_settings.items()}
                action = key_to_action.get(key_pressed)
                if action in valid_actions:
                    shout = Shout(player, action)
                    shouts.append(shout)
        shout_input = ShoutInput(shouts)
        return self.process_shout(shout_input)

    def process_shout(self, shout_input):
        shouts = shout_input.value
        duel = self.duel_ongoing
        round_ = duel.round_
        # Get only the first shout for each player
        red_shout_heard = False
        black_shout_heard = False
        for shout in shouts:
            if not red_shout_heard and shout.player == self.player_red:
                red_shout_heard = True
                self.player_red.recent_action = shout.action
            elif not black_shout_heard and shout.player == self.player_black:
                black_shout_heard = True
                self.player_black.recent_action = shout.action
            if red_shout_heard and black_shout_heard:
                break
        # priority: done > die > draw > dare (then offense > defense)
        for player in duel.players:
            valid_actions = player.valid_actions(round_)
            if constants.Action.DONE in valid_actions:
                if player.recent_action == constants.Action.DONE:
                    player.num_shout_done += 1
                    if player.is_done():  # correct done
                        duel.end(constants.DuelState.ABORTED_BY_CORRECT_DONE)
                        self._end(constants.GameResult.DONE, winner=player)
                        message = "{0} is done, so Duel #{1} is aborted.\n{0} wins! The game has ended as {0} first shouted done correctly.".format(
                            player.name, duel.index + 1)
                        duration = constants.Duration.AFTER_GAME_ENDS
                        return message, duration
        for player in duel.players:
            valid_actions = player.valid_actions(round_)
            if constants.Action.DIE in valid_actions:
                if player.recent_action == constants.Action.DIE:
                    player.num_shout_die += 1
                    duel.end(constants.DuelState.DIED)
                    message = "{} died, so no one gets a point. Duel #{} ended.".format(
                        player.name, duel.index + 1)
                    duration = constants.Duration.AFTER_DUEL_ENDS
                    return message, duration
        for player in duel.players:
            valid_actions = player.valid_actions(round_)
            if constants.Action.DRAW in valid_actions:
                if player.recent_action == constants.Action.DRAW:
                    player.num_shout_draw += 1
                    if duel.is_drawn():  # correct draw
                        duel.end(constants.DuelState.DRAWN, player)
                        message = '{} shouted draw correctly and gets a point. Duel #{} ended.'.format(
                            player.name, duel.index + 1)
                        duration = constants.Duration.AFTER_DUEL_ENDS
                        if duel.winner.points == constants.REQUIRED_POINTS:
                            self._end(constants.GameResult.FINISHED,
                                      winner=duel.winner)
                            message += "\n{0} wins! The game has ended as {0} first scored {1} points.".format(
                                duel.winner.name, constants.REQUIRED_POINTS)
                            duration = constants.Duration.AFTER_GAME_ENDS
                        return message, duration
        if round_ in (1, 2):
            duration = constants.Duration.BEFORE_CARD_OPEN
            message = "Ooh, double dare! Next cards will be opened in {} seconds!".format(
                duration)
            # do nothing and move on to next round to open next cards
            return message, duration
        elif round_ == 3:
            sum_offense = sum(card._value for card in duel.offense.deck_in_duel)
            sum_defense = sum(card._value for card in duel.defense.deck_in_duel)
            if sum_offense > sum_defense:
                duel.end(constants.DuelState.FINISHED, winner=duel.offense)
                message = '{0} has a greater sum, so {0} gets a point. Duel #{1} ended.'.format(
                    duel.winner.name, duel.index + 1)
            elif sum_offense < sum_defense:
                duel.end(constants.DuelState.FINISHED, winner=duel.defense)
                message = '{0} has a greater sum, so {0} gets a point. Duel #{1} ended.'.format(
                    duel.winner.name, duel.index + 1)
            else:
                duel.end(constants.DuelState.DRAWN, winner=duel.defense)
                message = "The sums are equal, but no one shouted draw, so the defense ({}) gets a point. Duel #{} ended.".format(
                    duel.winner.name, duel.index + 1)
            if duel.winner.points == constants.REQUIRED_POINTS:
                self._end(constants.GameResult.FINISHED, winner=duel.winner)
                message += "\n{0} wins! The game has ended as {0} first scored {1} points.".format(
                    duel.winner.name, constants.REQUIRED_POINTS)
                duration = constants.Duration.AFTER_GAME_ENDS
                return message, duration
            else:
                duration = constants.Duration.AFTER_DUEL_ENDS
                return message, duration
        raise ValueError('Invalid round.')

    def process_offense_deck_index_input(self, intra_duel_input):
        duel = self.duel_ongoing
        offense = duel.offense
        index = intra_duel_input.value
        offense_deck = offense.decks[index]
        if offense_deck.is_undisclosed():
            duel.summon(offense_deck)
            message = 'Deck #{} chosen as the offense deck.'.format(index + 1)
        else:
            message = 'Choose an undisclosed deck.'
        duration = constants.Duration.AFTER_DECK_CHOICE
        return message, duration

    def process_defense_deck_index_input(self, intra_duel_input):
        index = intra_duel_input.value
        duel = self.duel_ongoing
        defense_deck = duel.defense.decks[index]
        if defense_deck.is_undisclosed():
            duel.summon(defense_deck=defense_deck)
            message = 'Deck #{} chosen as the defense deck.'.format(index + 1)
        else:
            message = 'Choose an undisclosed deck.'
        duration = constants.Duration.AFTER_DECK_CHOICE
        return message, duration

    def _decide_offense_deck(self, prev_envstate=None):
        duel = self.duel_ongoing
        offense, defense = duel.players
        # Skip choosing deck in the last duel
        if self.duel_index == constants.DECK_PER_PILE - 1:
            offense_undisclosed_decks = offense.undisclosed_decks()
            deck = offense_undisclosed_decks[0]
            return OffenseDeckIndexInput(deck.index)
        else:
            deck_index = offense.decide_offense_deck_index(
                defense.decks, defense.points, defense.num_shout_die,
                prev_envstate)
            return OffenseDeckIndexInput(deck_index)

    def _decide_defense_deck(self, prev_envstate=None):
        duel = self.duel_ongoing
        offense, defense = duel.players
        # Skip choosing deck in the last duel
        if self.duel_index == constants.DECK_PER_PILE - 1:
            defense_undisclosed_decks = defense.undisclosed_decks()
            deck = defense_undisclosed_decks[0]
            return DefenseDeckIndexInput(deck.index)
        else:
            deck_index = offense.decide_defense_deck_index(
                defense.decks, defense.points, defense.num_shout_die,
                prev_envstate)
            return DefenseDeckIndexInput(deck_index)

    def _end(self, result, winner=None, loser=None):
        self._over = True
        self.result = result
        self.time_ended = time.time()
        self.winner = winner
        self.loser = loser
        if self.winner is None:
            if self.loser == self.player_black:
                self.winner = self.player_red
            else:
                self.winner = self.player_black
        elif self.loser is None:
            if self.winner == self.player_black:
                self.loser = self.player_red
            else:
                self.loser = self.player_black

    def distribute_piles(self):
        red_pile = RedPile()
        self.player_red.take_pile(red_pile)
        black_pile = BlackPile()
        self.player_black.take_pile(black_pile)

    def to_json(self):
        return jsonpickle.encode(self)

    def to_array(self, by_red=None):
        color = -1 if by_red is None else 0 if by_red else 1
        if by_red is None:  # observe both players' data
            red = list(self.player_red.to_array(public_only=False))
            black = list(self.player_black.to_array(public_only=False))
        elif by_red:  # observe from red's point of view
            red = list(self.player_red.to_array(public_only=False))
            black = list(self.player_black.to_array(public_only=True))
        else:  # observe from black's point of view
            red = list(self.player_red.to_array(public_only=True))
            black = list(self.player_black.to_array(public_only=False))
        if self.winner is None:
            winner = -1
        else:
            winner = int(self.winner == self.player_red)
        result = -1 if self.result is None else self.result.value
        duel_index = -1 if self.duel_index is None else self.duel_index
        common = [color, winner, result, duel_index]
        observation = numpy.array(red + black + common)
        return observation.reshape((1, -1))


class Player(object):
    def __init__(self, name=None, deck_in_duel_index=None, points=0,
                 num_shout_die=0, num_shout_done=0, num_shout_draw=0,
                 decks=None, pile=None, key_settings=None, alias=None,
                 recent_action=None, joker_value_strategy=None,
                 joker_position_strategy=None, offense_deck_index_strategy=None,
                 defense_deck_index_strategy=None, action_choice_strategy=None,
                 *args, **kwargs):
        self.name = name
        self._deck_in_duel_index = deck_in_duel_index
        self.deck_in_duel = None
        self.points = points
        self.num_shout_die = num_shout_die
        self.num_shout_done = num_shout_done
        self.num_shout_draw = num_shout_draw
        self.decks = decks
        self.pile = pile
        if key_settings is None:
            key_settings = {action: '' for action in constants.Action}
        self.key_settings = key_settings
        self.alias = alias
        self.recent_action = recent_action
        self.joker_value_strategy = joker_value_strategy
        self.joker_position_strategy = joker_position_strategy
        self.offense_deck_index_strategy = offense_deck_index_strategy
        self.defense_deck_index_strategy = defense_deck_index_strategy
        self.action_choice_strategy = action_choice_strategy

    @property
    def deck_in_duel_index(self):
        return self._deck_in_duel_index

    def valid_actions(self, round_):
        actions = [constants.Action.DONE]
        if round_ == 1:
            actions.append(constants.Action.DARE)
            if self.num_shout_die < constants.MAX_DIE:
                actions.append(constants.Action.DIE)
        elif round_ == 2:
            actions.append(constants.Action.DARE)
            if self.num_shout_die < constants.MAX_DIE:
                actions.append(constants.Action.DIE)
        elif round_ == 3:
            actions.append(constants.Action.IDLE)
            if self.num_shout_draw < constants.MAX_DRAW:
                actions.append(constants.Action.DRAW)
        else:
            raise ValueError('Something went wrong.')
        return actions

    def undisclosed_decks(self):
        return [deck for deck in self.decks if deck.is_undisclosed()]

    def revealed_joker(self):
        for deck in self.decks:
            for card in deck:
                if card.open_ and card._is_joker():
                    return True
        else:
            return False

    def take_pile(self, pile):
        if isinstance(pile, RedPile):
            self.pile = pile.cards
            self.alias = constants.PLAYER_RED
            self.key_settings = KeySettingsInput.bottom_left()
        elif isinstance(pile, BlackPile):
            self.pile = pile.cards
            self.alias = constants.PLAYER_BLACK
            self.key_settings = KeySettingsInput.top_right()
        else:
            raise ValueError('This is not a pile.')

    def build_decks(self):
        pile = list(self.pile)
        random.shuffle(pile)
        decks_previous = []
        for j in range(constants.DECK_PER_PILE):
            cards = []
            for k in range(constants.CARD_PER_DECK):
                new_card = pile.pop()
                cards.append(new_card)
            self.joker_value_strategy.apply(cards)
            self.joker_position_strategy.apply(cards)
            decks_previous.append(tuple(cards))
        decks_previous.sort(key=lambda x: x[0]._value)
        decks = []
        for index, cards in enumerate(decks_previous):
            deck = Deck(cards, index=index)
            deck.delegate.open_up()
            decks.append(deck)
        self.decks = tuple(decks)

    def reset(self):
        self._deck_in_duel_index = None
        self.deck_in_duel = None
        self.points = 0
        self.num_shout_die = 0
        self.num_shout_done = 0
        self.num_shout_draw = 0
        self.decks = None
        self.pile = None
        self.key_settings = {action: '' for action in constants.Action}
        self.alias = None
        self.recent_action = None

    @abc.abstractmethod
    def decide_offense_deck_index(self, decks_opponent, points_opponent,
                                  num_shout_die_opponent, prev_envstate=None):
        pass

    @abc.abstractmethod
    def decide_defense_deck_index(self, decks_opponent, points_opponent,
                                  num_shout_die_opponent, prev_envstate=None):
        pass

    def send_to_duel(self, deck, opponent_deck=None):
        self.deck_in_duel = deck
        self._deck_in_duel_index = deck.index
        deck.enter_duel(opponent_deck=opponent_deck)

    def open_next_card(self):
        deck = self.decks[self._deck_in_duel_index]
        if deck.card_to_open_index is None:
            deck.card_to_open_index = 1
        card_to_open = deck[deck.card_to_open_index]
        card_to_open.open_up()
        deck.card_to_open_index += 1
        if deck.card_to_open_index == 3:
            deck.card_to_open_index = None

    def is_done(self):
        disclosed_values = ComputerPlayer.disclosed_values(self.decks)
        num_disclosed_values = len(disclosed_values)
        num_all_values = len(constants.Rank)
        return num_disclosed_values == num_all_values

    def to_array(self, public_only=False):
        decks = [deck.to_array(public_only=public_only) for deck in self.decks]
        decks = list(itertools.chain.from_iterable(decks))
        points = -1 if self.points is None else self.points
        num_shout_die = -1 if self.num_shout_die is None else self.num_shout_die
        if self._deck_in_duel_index is None:
            deck_in_duel_index = -1
        else:
            deck_in_duel_index = self._deck_in_duel_index
        others = [points, num_shout_die, deck_in_duel_index]
        return numpy.array(decks + others)

    @classmethod
    def from_array(cls, array):
        decks_array = numpy.array(array[0:9 * 19])
        decks_reshaped = decks_array.reshape(9, -1)
        decks = [Deck.from_array(deck_array) for deck_array in decks_reshaped]
        points = None if array[9 * 19] == -1 else array[9 * 19]
        num_shout_die = None if array[9 * 19 + 1] == -1 else array[9 * 19 + 1]
        deck_in_duel_index = None if array[9 * 19 + 2] == -1 else array[
            9 * 19 + 2]
        return cls(decks=decks, points=points,
                   num_shout_die=num_shout_die,
                   deck_in_duel_index=deck_in_duel_index)


class HumanPlayer(Player):
    def __init__(self, prompt, forbidden_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = NameTextInput.from_human(prompt, forbidden_name).value
        self.joker_value_strategy = JokerValueStrategyTextInput.from_human(
            self.name).value
        self.joker_position_strategy = JokerPositionStrategyTextInput.from_human(
            self.name).value

    def decide_offense_deck_index(self, decks_opponent, points_opponent,
                                  num_shout_die_opponent, prev_envstate=None):
        undisclosed_decks = self.undisclosed_decks()
        deck_input = DeckTextInput.from_human(self.name, False,
                                              undisclosed_decks)
        return deck_input.value.index

    def decide_defense_deck_index(self, decks_opponent, points_opponent,
                                  num_shout_die_opponent, prev_envstate=None):
        undisclosed_decks = [deck for deck in decks_opponent if
                             deck.is_undisclosed()]
        deck_input = DeckTextInput.from_human(self.name, True,
                                              undisclosed_decks)
        deck = deck_input.value
        return deck.index

    def shout(self, decks_opponent, points_opponent, num_shout_die_opponent,
              round_, in_turn, duel_index, prev_envstate=None):
        allowed_actions = self.valid_actions(round_)
        keys_settings_in_list = ['{}: \'{}\''.format(action.name, key) for
                                 action, key in self.key_settings.items() if
                                 action in allowed_actions]
        keys_settings_in_str = ', '.join(keys_settings_in_list)
        prompt = '{}, what will you do? ({})'.format(self.name,
                                                     keys_settings_in_str)
        shout_input = input(constants.INDENT + prompt)
        key_to_action = {key: action for action, key in
                         self.key_settings.items()}
        for shout_str in shout_input:
            action = key_to_action.get(shout_str)
            if action is not None:
                return Shout(self, action)
        else:
            return Shout(self, None)


class ComputerPlayer(Player):
    def __init__(self, forbidden_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.name is None:
            self.name = NameTextInput.auto_generate(forbidden_name).value
        if self.joker_value_strategy is None:
            self.joker_value_strategy = RandomNumber
        if self.joker_position_strategy is None:
            self.joker_position_strategy = JokerAnywhere
        if self.offense_deck_index_strategy is None:
            self.offense_deck_index_strategy = AnyOffenseDeck
        if self.defense_deck_index_strategy is None:
            self.defense_deck_index_strategy = AnyDefenseDeck
        if self.action_choice_strategy is None:
            self.action_choice_strategy = SimpleActionChoiceStrategy

    def decide_offense_deck_index(self, decks_opponent, points_opponent,
                                  num_shout_die_opponent, prev_envstate=None):
        strategy = self.offense_deck_index_strategy
        deck = strategy.apply(self.decks, decks_opponent, self.points,
                              self.num_shout_die, points_opponent,
                              num_shout_die_opponent)
        return deck.index

    def decide_defense_deck_index(self, decks_opponent, points_opponent,
                                  num_shout_die_opponent, prev_envstate=None):
        strategy = self.defense_deck_index_strategy
        deck = strategy.apply(decks_opponent, self.decks, self.points,
                              self.num_shout_die, points_opponent,
                              num_shout_die_opponent)
        return deck.index

    @staticmethod
    def get_chances(decks_me, decks_opponent, is_opponent_red,
                    deck_in_duel_me=None,
                    deck_in_duel_opponent=None,
                    joker_value_strategy_me=SameAsMax):
        """get chances of winning, tying, and losing
        assuming the opponent uses SameAsMax as its joker value strategy
        """

        def guess_joker_value(delegate_value, joker_value_strategy=SameAsMax):
            """make an educated guess about the value of joker
            (There is no guarantee that the return value is correct.)
            """
            if joker_value_strategy == Thirteen:
                return 13
            elif joker_value_strategy == SameAsMax:
                return delegate_value
            elif joker_value_strategy == NextBiggest:
                return delegate_value - 1
            else:
                return random.randint(1, delegate_value)

        # get my hidden cards
        if deck_in_duel_me is None:
            deck_in_duel_me = next(
                deck for deck in decks_me if deck.is_in_duel())
        current_sum_me = sum(
            card._value for card in deck_in_duel_me if card.open_)
        delegate_value_me = deck_in_duel_me.delegate_value
        hidden_cards_me = []
        for deck in decks_me:
            for card in deck:
                if not card.open_:
                    if card._is_joker() or card._value <= delegate_value_me:
                        hidden_cards_me.append(card)
        # get the number of cards to open
        num_opened = sum(1 for card in deck_in_duel_me if card.open_)
        num_to_open = 3 - num_opened
        # get the opponent's hidden cards
        if deck_in_duel_opponent is None:
            deck_in_duel_opponent = next(
                deck for deck in decks_opponent if deck.is_in_duel())
        current_sum_opponent = sum(
            card._value for card in deck_in_duel_opponent if
            card.open_)
        delegate_value_opponent = deck_in_duel_opponent.delegate_value
        hidden_cards_opponent = []

        if is_opponent_red:
            entire_pile = RedPile()
            unopened_pile = RedUnopenedPile(entire_pile.cards)
        else:
            entire_pile = BlackPile()
            unopened_pile = BlackUnopenedPile(entire_pile.cards)
        for deck in decks_opponent:
            for card in deck:
                if card.open_:
                    try:
                        unopened_pile.remove(card)
                    except ValueError:
                        pass
        for card in unopened_pile:
            if card._is_joker() or card._value <= delegate_value_opponent:
                hidden_cards_opponent.append(card)
        # calculate the odds
        num_win, num_lose, num_draw = 0, 0, 0
        candidates_me = list(
            itertools.combinations(hidden_cards_me, num_to_open))
        candidates_opponent = list(itertools.combinations(hidden_cards_opponent,
                                                          num_to_open))
        for cards_me in candidates_me:
            for cards_opponent in candidates_opponent:
                # get my sum
                sum_me = current_sum_me
                for card in cards_me:
                    if card._is_joker():
                        sum_me += guess_joker_value(delegate_value_me,
                                                    joker_value_strategy_me)
                    else:
                        sum_me += card._value
                # get opponent's sum
                sum_opponent = current_sum_opponent
                for card in cards_opponent:
                    if card._is_joker():
                        sum_opponent += guess_joker_value(
                            delegate_value_opponent)
                    else:
                        sum_opponent += card._value
                # compare
                if sum_me > sum_opponent:
                    num_win += 1
                elif sum_me == sum_opponent:
                    num_draw += 1
                else:
                    num_lose += 1
        total = num_win + num_draw + num_lose
        odds_win = round(num_win / total, 3)
        odds_draw = round(num_draw / total, 3)
        odds_lose = round(num_lose / total, 3)
        return odds_win, odds_draw, odds_lose

    @classmethod
    def undisclosed_values(cls, decks):
        values = set(rank.value for rank in constants.Rank)
        disclosed_values = set(cls.disclosed_values(decks))
        undisclosed_values = values.difference(disclosed_values)
        return tuple(undisclosed_values)

    @staticmethod
    def disclosed_values(decks):
        values = set()
        for deck in decks:
            if not deck.is_undisclosed():
                for card in deck.cards:
                    if card.open_:
                        values.add(card._value)
        return tuple(values)

    def shout(self, decks_opponent, points_opponent, num_shout_die_opponent,
              round_, in_turn, duel_index, prev_envstate=None):
        strategy = self.action_choice_strategy
        is_opponent_red = in_turn ^ (duel_index % 2 == 0)
        action = strategy.apply(round_, in_turn, self.decks, decks_opponent,
                                self.num_shout_die, is_opponent_red,
                                num_shout_die_opponent, self.points,
                                points_opponent)
        return Shout(self, action)


class DieBlindButSmart(ComputerPlayer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.joker_value_strategy = Thirteen
        self.joker_position_strategy = JokerAnywhere
        self.offense_deck_index_strategy = BiggestOffenseDeck
        self.defense_deck_index_strategy = SmallestDefenseDeck


class AntiDie(ComputerPlayer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.joker_value_strategy = Thirteen
        self.joker_position_strategy = JokerAnywhere
        self.offense_deck_index_strategy = BiggestOffenseDeck
        self.defense_deck_index_strategy = StatsConsideredBiggest


class Card(object):
    def __init__(self, suit, colored, rank, value=None, open_=False):
        self._suit = suit
        self._colored = colored
        self._rank = rank
        self._value = value
        self.open_ = open_

    def __eq__(self, other):
        same_suit = self._suit == other._suit
        same_color = self._colored == other._colored
        same_rank = self._rank == other._rank
        return same_suit and same_color and same_rank

    def __repr__(self):
        if self._is_joker():
            colored = 'Colored' if self._colored else 'Black'
            rank = self._rank
            representation = '{} {}'.format(colored, rank)
        else:
            representation = '{} of {}'.format(self._rank, self._suit.name)
        if not self.open_:
            representation = '({})'.format(representation)
        return representation

    def __str__(self):
        if self.open_:
            initial = 'J' if self._is_joker() else self._suit.name[0]
            return '{} {}'.format(self._value, initial)
        else:
            return '?'

    def open_up(self):
        self.open_ = True

    def _is_joker(self):
        return self._rank == constants.JOKER

    def to_array(self, public_only=False):
        assert self.open_ is not None
        if not self.open_ and public_only:
            suit = -1
            colored = -1 if self._colored is None else int(self._colored)
            rank = -1
            value = -1
            open_ = int(self.open_)
            list_ = [suit, colored, rank, value, open_]
            return numpy.array(list_)
        else:
            suit = -1 if self._suit is None else self._suit.value
            colored = -1 if self._colored is None else int(self._colored)
            if self._rank is None:
                rank = -1
            elif self._is_joker():
                rank = 0
            else:
                rank = constants.Rank[self._rank].value
            value = -1 if self._value is None else self._value
            open_ = -1 if self.open_ is None else int(self.open_)
            list_ = [suit, colored, rank, value, open_]
            return numpy.array(list_)

    @classmethod
    def from_array(cls, array):
        suit, colored, rank, value, open_ = tuple(array)
        suit = None if suit == -1 else constants.Suit(suit)
        colored = None if colored == -1 else bool(colored)
        rank = None if rank == -1 else constants.Rank(rank)
        value = None if value == -1 else value
        open_ = None if open_ == -1 else bool(open_)
        return cls(suit, colored, rank, value, open_)


class Deck(object):
    def __init__(self, cards, state=constants.DeckState.UNDISCLOSED, index=None,
                 opponent_deck_index=None, card_to_open_index=None):
        self._state = state
        self._cards = cards
        self._index = index  # zero based
        self._opponent_deck_index = opponent_deck_index
        self.card_to_open_index = card_to_open_index

    def __str__(self):
        return ' / '.join(str(card) for card in self._cards)

    def __getitem__(self, index):
        return self._cards[index]

    def mask_if_undisclosed(self):
        if self.is_undisclosed():
            return '', '', ''
        else:
            return tuple(str(card) for card in self)

    def show_undisclosed_delegate(self):
        if self.is_undisclosed():
            return str(self.delegate)
        else:
            return ''

    @property
    def index(self):
        return self._index

    @property
    def cards(self):
        return self._cards

    @property
    def state(self):
        return self._state

    @property
    def opponent_deck_index(self):
        return self._opponent_deck_index

    @property
    def delegate(self):
        return self._cards[0]

    @property
    def delegate_value(self):
        return self.delegate._value

    def is_undisclosed(self):
        return self._state == constants.DeckState.UNDISCLOSED

    def is_in_duel(self):
        return self._state == constants.DeckState.IN_DUEL

    def enter_duel(self, opponent_deck=None):
        self._state = constants.DeckState.IN_DUEL
        if opponent_deck is not None:
            self.meet_opponent(opponent_deck)
            opponent_deck.meet_opponent(self)

    def meet_opponent(self, opponent_deck):
        self._opponent_deck_index = opponent_deck.index

    def finish(self):
        self._state = constants.DeckState.FINISHED

    def to_array(self, public_only=False):
        if self._cards is None:
            cards_flattened = []
        else:
            cards_list = [card.to_array(public_only=public_only) for card in
                          self._cards]
            cards = numpy.array(cards_list)
            cards_flattened = cards.flatten()
        state = -1 if self._state is None else self._state.value
        index = -1 if self._index is None else self._index
        if self._opponent_deck_index is None:
            opponent_deck_index = -1
        else:
            opponent_deck_index = self._opponent_deck_index
        if self.card_to_open_index is None:
            card_to_open_index = -1
        else:
            card_to_open_index = self.card_to_open_index
        list_ = [*cards_flattened, state, index, opponent_deck_index,
                 card_to_open_index]
        return numpy.array(list_)

    @classmethod
    def from_array(cls, array):
        cards = [array[0:5], array[5:10], array[10:15]]
        state = array[15]
        index = array[16]
        opponent_deck_index = array[17]
        card_to_open_index = array[18]
        cards_flattened = numpy.array(cards).flatten()
        if cards_flattened:
            cards = [Card.from_array(card_array) for card_array in cards]
        else:
            cards = None
        state = None if state == -1 else constants.DeckState(state)
        index = None if index == -1 else index
        if opponent_deck_index == -1:
            opponent_deck_index = None
        if card_to_open_index == -1:
            card_to_open_index = None
        return cls(cards, state, index, opponent_deck_index, card_to_open_index)


class Duel(object):
    def __init__(self, player_red, player_black, index, time_started=None,
                 round_=1, over=False, time_ended=None, winner=None, loser=None,
                 state=constants.DuelState.UNSTARTED, offense=None,
                 defense=None):
        self.player_red = player_red
        self.player_black = player_black
        self._index = index
        if time_started is None:
            self.time_started = time.time()
        else:
            self.time_started = time_started
        self._round = round_
        self._over = over
        self.time_ended = time_ended
        self.winner = winner
        self.loser = loser
        self._state = state
        if offense is None:
            if self._index % 2 == 0:
                self.offense = self.player_red
            else:
                self.offense = self.player_black
        else:
            self.offense = offense
        if defense is None:
            if self._index % 2 == 0:
                self.defense = self.player_black
            else:
                self.defense = self.player_red
        else:
            self.defense = defense

    @property
    def players(self):
        return self.offense, self.defense

    @property
    def index(self):
        return self._index

    @property
    def round_(self):
        return self._round

    def to_next_round(self):
        self._round += 1

    def start(self):
        self._state = constants.DuelState.ONGOING

    def summon(self, offense_deck=None, defense_deck=None):
        offense, defense = self.players
        if offense_deck is not None:
            offense.send_to_duel(offense_deck)
        elif defense_deck is not None:
            if offense_deck is None:
                offense_deck = offense.deck_in_duel
            defense.send_to_duel(defense_deck, opponent_deck=offense_deck)
        else:
            raise Exception(
                'Either the offense deck or the defense deck must be supplied.')

    def is_drawn(self):
        sum_offense = sum(card._value for card in self.offense.deck_in_duel)
        sum_defense = sum(card._value for card in self.defense.deck_in_duel)
        return sum_offense == sum_defense

    def is_over(self):
        return self._over

    def end(self, state, winner=None, loser=None):
        self._over = True
        self.time_ended = time.time()
        if state.value not in range(3, 11):
            raise ValueError('Invalid DeckState.')
        self._state = state
        self.winner = winner
        self.loser = loser
        if self.winner is None and self.loser is None:
            if state not in (constants.DuelState.DIED,
                             constants.DuelState.ABORTED_BY_CORRECT_DONE,
                             constants.DuelState.ABORTED_BY_WRONG_CHOICE):
                raise ValueError('Either winner or loser must be supplied.')
        else:
            if winner is None:
                if loser == self.offense:
                    self.winner = self.defense
                else:
                    self.winner = self.offense
            elif loser is None:
                if winner == self.offense:
                    self.loser = self.offense
                else:
                    self.loser = self.defense
            self.winner.points += 1
        for player in self.players:
            if player.deck_in_duel is not None:
                player.deck_in_duel.finish()
                for card in player.deck_in_duel:
                    card.open_up()
                player.deck_in_duel = None


class Pile(object):
    pass


class UnopenedPile(collections.UserList):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for card in self:
            card.open_up()


class RedUnopenedPile(UnopenedPile):
    pass


class BlackUnopenedPile(UnopenedPile):
    pass


class RedPile(Pile):
    def __init__(self, cards=None):
        if cards is None:
            red_joker = Card(None, True, constants.JOKER, None, False)
            cards = [red_joker]
            red_suits = (suit for suit in constants.Suit if suit.value % 2 == 0)
            for suit in red_suits:
                for rank in constants.Rank:
                    card = Card(suit, True, rank.name, rank.value, False)
                    cards.append(card)
            self._cards = tuple(cards)
        else:
            self._cards = cards

    def __contains__(self, item):
        return item in self.cards

    @property
    def cards(self):
        return self._cards


class BlackPile(Pile):
    def __init__(self):
        black_joker = Card(None, False, constants.JOKER, None, False)
        cards = [black_joker]
        black_suits = (suit for suit in constants.Suit if suit.value % 2 == 1)
        for suit in black_suits:
            for rank in constants.Rank:
                card = Card(suit, False, rank.name, rank.value, False)
                cards.append(card)
        self._cards = cards

    @property
    def cards(self):
        return self._cards


class OutputHandler(object):
    def __init__(self):
        self.states = []
        self.messages = []

    def save(self, game_state_in_json, message):
        self.states.append(game_state_in_json)
        self.messages.append(message)

    @staticmethod
    def display(game_state_in_json=None, message='', duration=0):
        column_width = 9
        total_width = column_width * constants.DECK_PER_PILE
        name_format = '{} ({})'
        stats_format = 'Points {} | Die {}'

        def center(content, width, fill=''):
            return '{:{}^{}}'.format(content, fill, width)

        def to_line(iterable):
            aligned = (center(elem, column_width) for elem in iterable)
            return ''.join(aligned)

        divider = center('', total_width, fill='-')
        print(divider)
        if game_state_in_json is None and message:
            message_delimited = message.split('\n')
            print('Message:  {}'.format(message_delimited[0]))
            for line in message_delimited[1:]:
                print('{}{}'.format(constants.INDENT, line))
            time.sleep(duration)
            return
        game = jsonpickle.decode(game_state_in_json)
        duel = game.duel_ongoing
        red_role = '' if duel is None else (
            'Offense' if game.player_red == duel.offense else 'Defense')
        red_name = name_format.format(game.player_red.name,
                                      game.player_red.alias)
        red_stats = stats_format.format(game.player_red.points,
                                        game.player_red.num_shout_die)
        red_role_aligned = center(red_role, column_width * 2)
        red_name_aligned = center(red_name, column_width * 5)
        red_stats_aligned = center(red_stats, column_width * 2)
        red_first_line = '{}{}{}'.format(red_role_aligned, red_name_aligned,
                                         red_stats_aligned)
        print(red_first_line)
        red_decks = game.player_red.decks
        red_numbers = (('< #{} >' if deck.is_in_duel() else '#{}').format(
            deck.index + 1) for deck in red_decks)
        red_number_line = to_line(red_numbers)
        print(red_number_line)
        red_undisclosed_delegates = (deck.show_undisclosed_delegate() for deck
                                     in red_decks)
        row_undisclosed_delegate_line = to_line(red_undisclosed_delegates)
        print(row_undisclosed_delegate_line)
        red_opened_delegates = (deck.mask_if_undisclosed()[0] for deck in
                                red_decks)
        row_opened_delegates_line = to_line(red_opened_delegates)
        print(row_opened_delegates_line)
        red_seconds = (deck.mask_if_undisclosed()[1] for deck in red_decks)
        row_seconds_line = to_line(red_seconds)
        print(row_seconds_line)
        red_lasts = (deck.mask_if_undisclosed()[2] for deck in red_decks)
        red_lasts_line = to_line(red_lasts)
        print(red_lasts_line)
        print()
        duel_str = '' if duel is None else '[Duel #{}]'.format(duel.index + 1)
        duel_line = center(duel_str, total_width)
        print(duel_line)
        print()
        black_decks = game.player_black.decks
        black_lasts = (deck.mask_if_undisclosed()[2] for deck in black_decks)
        print(to_line(black_lasts))
        black_seconds = (deck.mask_if_undisclosed()[1] for deck in black_decks)
        print(to_line(black_seconds))
        black_opened_delegates = (deck.mask_if_undisclosed()[0] for deck in
                                  black_decks)
        print(to_line(black_opened_delegates))
        black_undisclosed_delegates = (deck.show_undisclosed_delegate() for deck
                                       in black_decks)
        black_undisclosed_delegates_line = to_line(black_undisclosed_delegates)
        print(black_undisclosed_delegates_line)
        black_numbers = (
            ('< #{} >' if deck.is_in_duel() else '#{}').format(
                deck.index + 1) for deck in black_decks)
        black_number_line = to_line(black_numbers)
        print(black_number_line)
        black_role = '' if duel is None else (
            'Offense' if game.player_black == duel.offense else 'Defense')
        black_name = name_format.format(game.player_black.name,
                                        game.player_black.alias)
        black_stats = stats_format.format(game.player_black.points,
                                          game.player_black.num_shout_die)
        black_role_aligned = center(black_role, column_width * 2)
        black_name_aligned = center(black_name, column_width * 5)
        black_stats_aligned = center(black_stats, column_width * 2)
        black_first_line = '{}{}{}'.format(black_role_aligned,
                                           black_name_aligned,
                                           black_stats_aligned)
        print(black_first_line)
        if message:
            message_delimited = message.split('\n')
            print('Message:  {}'.format(message_delimited[0]))
            for line in message_delimited[1:]:
                print('{}{}'.format(constants.INDENT, line))
        time.sleep(duration)

    @staticmethod
    def extract_file_name(game_state_in_json):
        game = jsonpickle.decode(game_state_in_json)
        red_class = game.player_red.__class__.__name__
        red_name = game.player_red.name
        black_class = game.player_black.__class__.__name__
        black_name = game.player_black.name
        time_started_str = game.time_started
        time_started_float = float(time_started_str)
        datetime_started = datetime.datetime.fromtimestamp(time_started_float)
        datetime_str = datetime.datetime.strftime(datetime_started,
                                                  '%Y%m%d%H%M%S')
        file_name = '{}({}){}({}){}.json'.format(red_class, red_name,
                                                 black_class, black_name,
                                                 datetime_str)
        return file_name

    @staticmethod
    def export_json_to_file(game_state_json, file_path, final_state_only=False):
        with open(file_path, 'w') as file:
            if final_state_only:
                final_state = game_state_json[-1:]
                json.dump(final_state, file)
            else:
                json.dump(game_state_json, file)

    def export_game_states(self, file_location=None, file_name=None,
                           final_state_only=False):
        if not self.states:
            raise Exception('No game states found in this OutputHandler.')
        if file_location is None:
            current_file_path = os.path.abspath(__file__)
            current_directory_path = os.path.dirname(current_file_path)
            directory_name = 'json'
            file_location = os.path.join(current_directory_path, directory_name)
            if not os.path.exists(file_location):
                os.makedirs(file_location)
        if file_name is None:
            last_game_state = self.states[-1]
            file_name = self.extract_file_name(last_game_state)
        file_path = os.path.join(file_location, file_name)
        self.export_json_to_file(self.states, file_path, final_state_only)

    def import_from_json(self, file_path):
        with open(file_path) as file:
            content = file.read()
            self.states = jsonpickle.decode(content)


def main(num_human_players=1, suppress_output=False, save_all=False,
         save_result=False):
    output_handler = OutputHandler()

    if num_human_players == 2:
        player1 = HumanPlayer('Player 1, enter your name: ')
        player2 = HumanPlayer('Player 2, enter your name: ', player1.name)
    elif num_human_players == 1:
        player1 = HumanPlayer('Player 1, enter your name: ')
        player2 = ComputerPlayer(player1.name)
    elif num_human_players == 0:
        player1 = ComputerPlayer()
        player2 = ComputerPlayer(player1.name)
    else:
        raise Exception('Invalid number of human players')

    # red/black decision
    if not suppress_output:
        message = "All right, {} and {}. Let's get started!".format(
            player1.name, player2.name)
        message += '\nLet\'s flip a coin to decide who will be the Player Red!'
        duration = constants.Duration.BEFORE_COIN_TOSS
        output_handler.display(message=message, duration=duration)

    player_red, player_black = RandomPlayerOrder(player1, player2).players
    # player_red, player_black = player1, player2

    if not suppress_output:
        message = '{}, you are the Player Red, so you will go first.'.format(
            player_red.name)
        message += '\n{}, you are the Player Black.'.format(player_black.name)
        duration = constants.Duration.AFTER_COIN_TOSS
        output_handler.display(message=message, duration=duration)

    game = Game(player_red, player_black)
    game.distribute_piles()
    game.build_decks()

    if not suppress_output:
        message = "Let's start DieOrDare!\nHere we go!"
        duration = constants.Duration.BEFORE_GAME_START
        output_handler.display(message=message, duration=duration)

    while not game.is_over():
        duel = game.to_next_duel()
        while not duel.is_over():
            message, duration = game.prepare()
            if save_all or save_result:
                output_handler.save(game.to_json(), message)
            if not suppress_output:
                output_handler.display(game.to_json(), message, duration)
            user_input = game.accept()
            message, duration = game.process(user_input)
            if save_all or save_result:
                output_handler.save(game.to_json(), message)
            if not suppress_output:
                output_handler.display(game.to_json(), message, duration)
    if save_all:
        output_handler.export_game_states(final_state_only=False)
    elif save_result:
        output_handler.export_game_states(final_state_only=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enjoy my game!')
    parser.add_argument('--humans', help='number of human players',
                        type=int, choices=[0, 1, 2], default=1)
    parser.add_argument('-q', '--quiet', help='suppress command-line output',
                        action='store_true')
    parser.add_argument('-r', '--repeat', help='number of games to play',
                        type=int, default=1)  # silently ignores negative inputs
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--save-all', action='store_true',
                       help='save all command-line output to a JSON file')
    group.add_argument('--save-result-only', action='store_true',
                       help='save only the result to a JSON file')
    arguments = parser.parse_args()
    for trial_index in range(arguments.repeat):
        if arguments.repeat > 1:
            print('Game #{}'.format(trial_index + 1))
        main(arguments.humans, arguments.quiet, arguments.save_all,
             arguments.save_result_only)
