import random
from solders.keypair import Keypair
import codecs


def generate_wallet():
    return Keypair()


def get_secretkey_from_keypair(kp: Keypair):
    return "".join(codecs.encode(bytes(kp), 'base64').decode().splitlines())


def calculate_random_amounts(total_amount: int, num_wallets: int):
    amounts = []
    for _ in range(num_wallets - 1):
        amounts.append(random.uniform(1, total_amount - sum(amounts)))
    amounts.append(total_amount - sum(amounts))
    return amounts
