class DomainError(Exception):
    pass


class PoisonMessageError(DomainError):
    pass


class InsufficientFundsError(DomainError):
    pass


class MerchantNotFoundError(DomainError):
    pass
