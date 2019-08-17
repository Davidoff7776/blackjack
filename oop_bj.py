import os
import random
import typing as t
from enum import Enum
from functools import partial
from getpass import getpass
from itertools import product
from secrets import token_hex
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

import attr
import bcrypt
import psycopg2


attrs = partial(attr.s, auto_attribs=True, slots=True)
State = Enum("State", "IDLE ACTIVE STAND BUST")


def clear_console():
    print("\033[2J")


def start_choice():
    while True:
        ans = input(
            "\nWhat do you want to do?\n[1] - Start playing\n[2] - Display the top\n> "
        )
        if ans in ("1", "2"):
            return ans == "1"


def ask_question(question):
    while True:
        print(f"{question} (y/n)?")
        ans = input("> ").lower()
        if ans in ("y", "n"):
            return ans == "y"


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


def get_user_credentials():
    clear_console()
    while True:
        email = input("Email address (max. 255 chars.):\n> ")
        password = getpass("Password (min. 6/max. 1000 chars.):\n> ").encode("utf8")
        if len(email) < 255 and 1000 > len(password) > 5 and "@" in email:
            return email, password
        print("Please input valid credentials.")


def email_code(recipient):
    code = token_hex(4)
    message = Mail(
        from_email="bot@blackjack",
        to_emails=recipient,
        subject="Blackjack Game Email Confirmation Code",
        html_content=code,
    )
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
        print("The confirmation code has been sent to your email address.")
        return code
    except Exception as e:
        print(str(e))


def build_deck():
    suits = ("Hearts", "Clubs", "Diamonds", "Spades")
    values = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
    return [Card(value, suit) for value, suit in product(values, suits)]


@attrs
class Card:

    value: str
    suit: str

    def score(self):
        if self.value in ("J", "Q", "K"):
            return 10
        elif self.value == "A":
            return 1
        else:
            return int(self.value)

    def __str__(self):
        return f"{self.value} of {self.suit}"


@attrs
class Shoe:

    cards: t.List[Card] = attr.ib(factory=build_deck)

    def shuffle(self):
        random.shuffle(self.cards)

    def draw_card(self):
        return self.cards.pop()

    def __str__(self):
        cards = [str(c) for c in self.cards]
        return str(cards)


@attrs
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


@attrs
class Player:

    budget: int  # Number of money for bets
    bet: int = attr.ib(default=None)  # Money bet
    hand: Hand = attr.ib(factory=Hand)  # Player's hand
    state: State = attr.ib(default=State.IDLE)  # can be IDLE, ACTIVE, STAND or BUST

    def player_bet(self):
        if self.is_broke():
            raise Exception("Unfortunately you don't have any money.")
        self.bet = ask_bet(self.budget)

    def update(self):
        """ Update self.state after self.hit
        If player busted, self.state = State.BUST, etc.
        """
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


@attrs
class Dealer:

    shoe: Shoe = attr.ib(factory=Shoe)
    hand: Hand = attr.ib(factory=Hand)
    state: State = attr.ib(default=State.IDLE)
    MINIMUM_SCORE: int = attr.ib(default=17)

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
        elif hand_score >= self.MINIMUM_SCORE:
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
        if self.hand.score() < self.MINIMUM_SCORE:
            self.hit()
            self.update()

    def deal(self, player, game):
        """ In this method, the dealer and player enter a loop in which the
        player gets a card from the dealer until it stands or busts.
        """
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


@attrs
class Database:

    email: str
    password: str
    sql_id: int = attr.ib(default=None)
    budget: int = attr.ib(default=None)
    conn: t.Any = attr.ib(default=psycopg2.connect(""))
    cur: t.Any = attr.ib(default=None)

    def check_account(self):
        self.cur.execute("SELECT id FROM users WHERE email=%s", (self.email,))
        return bool(self.cur.fetchone())

    def login(self):
        self.cur.execute("SELECT password FROM users WHERE email=%s", (self.email,))
        credentials = self.cur.fetchone()
        correct_hash = credentials[0].encode("utf8")
        if bcrypt.checkpw(self.password, correct_hash):
            print("You have successfully logged-in!")
        else:
            raise Exception("You have failed logging-in!")

    def register(self):
        code = email_code(self.email)
        user_code = input("Please input the code sent to your email:\n>")
        if code != user_code:
            raise Exception("Invalid code.")
        hashed_pw = bcrypt.hashpw(self.password, bcrypt.gensalt()).decode("utf8")
        self.cur.execute(
            "INSERT into users (email, password) VALUES (%s, %s)",
            (self.email, hashed_pw),
        )

    def initialize(self):
        with self.conn:
            self.cur = self.conn.cursor()
            checked = self.check_account()
            if checked:
                self.login()
            else:
                self.register()
                print("You have successfully registered and received $1000 as a gift!")
            self.cur.execute(
                "SELECT ID, budget FROM users WHERE email=%s", (self.email,)
            )
            sql_id_budget = self.cur.fetchone()
            self.sql_id = sql_id_budget[0]
            self.budget = sql_id_budget[1]

    def display_top(self):
        self.cur.execute("SELECT email, budget FROM users ORDER BY budget DESC")
        top = self.cur.fetchall()
        places = range(1, len(top) + 1)
        for (a, b), i in zip(top, places):
            print(f"{i}. {a} - ${b}")

    def update_budget(self):
        self.cur.execute(
            "UPDATE users SET budget=%s WHERE id=%s", (self.budget, self.sql_id)
        )
        self.conn.commit()


@attrs
class Game:

    player: Player
    dealer: Dealer = attr.ib(factory=Dealer)

    def reset_attributes(self):
        # Reset hands, states, shoe
        self.player.hand.cards = []
        self.player.state = State.IDLE
        self.dealer.hand.cards = []
        self.dealer.state = State.IDLE
        self.dealer.shoe = Shoe()

    def open(self):

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

    def close(self):
        # Pay/charge the player according to cards result
        dealer_score = self.dealer.hand.score()
        if not self.player.is_busted():

            if self.dealer.state == State.BUST:
                self.player.budget += self.player.bet
            else:
                if self.player.hand.score() < dealer_score:
                    self.player.budget -= self.player.bet
                elif self.player.hand.score() > dealer_score:
                    self.player.budget += self.player.bet
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
    email, password = get_user_credentials()
    database = Database(email, password)
    database.initialize()
    if start_choice():
        player = Player(database.budget)
        game = Game(player)
        playing = True
        while playing:
            game.run()
            database.budget = player.budget
            database.update_budget()
            playing = ask_question("\nDo you want to play again")
            if playing:
                game.reset_attributes()
            else:
                database.cur.close()
    else:
        database.display_top()


if __name__ == "__main__":
    main()
