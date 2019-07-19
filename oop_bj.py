import random
import typing as t
from enum import Enum
from functools import partial
import os
import attr


lock = partial(attr.s, auto_attribs=True, slots=True)
State = Enum("State", "IDLE ACTIVE STAND BUST")


def ask_question(question):
    while True:
        print(f"{question} [y/n]?")
        ans = input("> ").casefold()
        if ans in ("y", "n"):
            return ans == "y"


def clear_console():
    os.system("cls" if os.name == "nt" else "clear")


def ask_bet(budget):
    clear_console()
    print(f"Money: ${budget}")
    print("How much money do you want to bet?")
    while True:
        money_bet = input("> ")
        try:
            cash_bet = int(money_bet)
        except ValueError:
            cash_bet = -1
        if budget >= cash_bet > 0:
            return cash_bet
        print("Please input a valid bet.")


def build_deck():
    suits = ["Hearts", "Clubs", "Diamonds", "Spades"]
    values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    cards = [Card(value, suit) for value in values for suit in suits]
    return cards


@lock
class Card:

    value: str
    suit: str

    def score(self):
        if self.value in "JQK":
            return 10
        elif self.value == "A":
            return 1
        else:
            return int(self.value)

    def __str__(self):
        return f"{self.value} of {self.suit}"


@lock
class Shoe:

    cards: t.List[Card] = attr.ib(factory=build_deck)

    def shuffle(self):
        random.shuffle(self.cards)

    def draw_card(self):
        return self.cards.pop()

    def __str__(self):
        cards = [str(c) for c in self.cards]
        return str(cards)


@lock
class Hand:
    # A collection of cards that a player get from the dealer in a game
    cards: t.List[Card] = attr.ib(default=[])

    def add(self, card):
        self.cards.append(card)

    def score(self):
        # Value of cards at hand
        total = sum(card.score() for card in self.cards)

        if any(card.value == "A" for card in self.cards) and total <= 11:
            total += 10

        return total

    def __str__(self):
        return "{} ({})".format(
            "".join("[{}]".format(card.value) for card in self.cards), self.score()
        )


@lock
class Player:

    budget: int  # Number of money for bets
    bet: int = attr.ib(default=None)  # Money bet
    hand: Hand = attr.ib(factory=Hand)  # Player's hand
    state: State = attr.ib(default=State.IDLE)  # can be IDLE, ACTIVE, STAND or BUST

    def player_bet(self):
        self.bet = ask_bet(self.budget)

    """ Update self.state after self.hit
        If player busted, self.state = State.BUST, etc.
    """

    def update(self):
        hand_score = self.hand.score()
        if hand_score > 21:
            self.state = State.BUST
        elif hand_score == 21:
            self.state = State.STAND
        else:
            self.state = State.ACTIVE

    def is_busted(self):
        return self.state == State.BUST

    def is_standing(self):
        return self.state == State.STAND

    def is_idle(self):
        return self.state == State.IDLE

    def is_broke(self):
        return self.budget == 0

    def hit(self, dealer):
        # Ask dealer to add a card to the hand (at their turn)
        card = dealer.draw_card()
        self.hand.add(card)

    def play(self, dealer):
        if ask_question("Do you want to hit"):
            # Player hits
            self.hit(dealer)
            self.update()
        else:
            self.state = State.STAND

    def __str__(self):
        return f"Player Info:\nBudget: {self.budget}\nMoney bet: {self.bet}\nHand: {self.hand}"


@lock
class Dealer:

    shoe: Shoe = attr.ib(factory=Shoe)
    hand: Hand = attr.ib(factory=Hand)
    state: State = attr.ib(default=State.IDLE)

    def draw_card(self):  # Delegate method
        card = self.shoe.draw_card()
        return card

    def hit(self):
        card = self.draw_card()
        self.hand.add(card)

    def update(self):
        hand_score = self.hand.score()
        if hand_score > 21:
            self.state = State.BUST
        elif hand_score >= 17:
            self.state = State.STAND
        else:
            self.state = State.ACTIVE

    def is_busted(self):
        return self.state == State.BUST

    def is_standing(self):
        return self.state == State.STAND

    def is_idle(self):
        return self.state == State.IDLE

    def play(self):
        if self.hand.score() < 17:
            self.hit()
            self.update()

    """ In this method, the dealer and player enter a loop
        In which the player hits a card from the dealer until it stands or busts
    """

    def deal(self, player, game):
        while True:
            player.play(self)
            game.display_info()
            if player.is_busted() or player.is_standing():
                break

    def display_cards(self, player, game):
        if game.is_finished():
            return f"Dealer Info:\nHand:{self.hand}"
        elif player.state == State.ACTIVE:
            return f"Dealer Info:\nHand: [{self.hand.cards[0]}][?]"


@lock
class Game:

    player: Player
    dealer: Dealer = attr.ib(factory=Dealer)

    def reset_attributes(self):
        self.player.hand.cards = []
        self.player.state = State.IDLE
        self.dealer.hand.cards = []
        self.dealer.state = State.IDLE
        self.dealer.shoe = Shoe()

    def open(self):
        if self.player.is_broke():
            raise Exception("Unfortunately you don't have any money.")

        self.player.player_bet()

        self.dealer.shoe.shuffle()

        c1 = self.dealer.draw_card()
        c2 = self.dealer.draw_card()
        self.player.hand = Hand([c1, c2])
        self.player.update()  # Update player state

        # The dealer is the last one to get cards
        c1 = self.dealer.draw_card()
        c2 = self.dealer.draw_card()
        self.dealer.hand = Hand([c1, c2])
        self.dealer.update()

        self.display_info()

    def is_finished(self):
        if self.dealer.hand.score() >= 21:
            return True
        if self.player.is_busted() or self.player.is_standing():
            return True

    """ Pay/charge the player according to cards result
        Reset hands, states, shoe
    """

    def close(self):
        dealer_score = self.dealer.hand.score()
        if not self.player.is_busted():

            if self.dealer.state == State.BUST:
                self.player.budget += self.player.bet * 2
            else:
                if self.player.hand.score() < dealer_score:
                    self.player.budget -= self.player.bet
                elif self.player.hand.score() > dealer_score:
                    self.player.budget += self.player.bet * 2
        else:
            self.player.budget -= self.player.bet

        self.display_info()

    def run(self):
        # Run a full game, from open() to close()
        self.open()

        # If the dealer has a blackjack, close the game
        if self.is_finished():
            self.close()
            return

        # The dealer deals with the player
        self.dealer.deal(self.player, self)

        # Now the dealer's turn to play ...
        while True:
            self.dealer.play()
            if self.dealer.is_busted() or self.dealer.is_standing():
                break

        self.close()

    def display_info(self):
        clear_console()
        print(f"{self.player}\n")
        print(f"{self.dealer.display_cards(self.player, self)}\n")
        player_score = self.player.hand.score()
        dealer_score = self.dealer.hand.score()
        if player_score == 21:
            print("Blackjack! You won!")
        elif dealer_score == 21:
            print("Dealer has got a blackjack. You lost!")
        elif self.player.is_busted():
            print("Busted! You lost!")
        elif self.player.is_standing():
            if self.dealer.is_busted():
                print("Dealer busted! You won!")
            elif player_score > dealer_score:
                print("You beat the dealer! You won!")
            elif player_score < dealer_score:
                print("Dealer has beaten you. You lost!")
            else:
                print("Push. Nobody wins or losses.")


def main():
    playing = True
    p = Player(1000)
    g = Game(p)
    while playing:
        g.run()
        playing = ask_question("\nDo you want to play again")
        if playing:
            g.reset_attributes()


if __name__ == "__main__":
    main()
