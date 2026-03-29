from dataclasses import dataclass


@dataclass(frozen=True)
class IssuerAlias:
    alias: str
    company_name: str
    ticker: str


ISSUER_ALIASES: tuple[IssuerAlias, ...] = (
    IssuerAlias("APPLE", "Apple", "AAPL"),
    IssuerAlias("MICROSOFT", "Microsoft", "MSFT"),
    IssuerAlias("ALPHABET", "Alphabet", "GOOGL"),
    IssuerAlias("GOOGLE", "Google", "GOOGL"),
    IssuerAlias("META", "Meta", "META"),
    IssuerAlias("AMAZON", "Amazon", "AMZN"),
    IssuerAlias("NVIDIA", "NVIDIA", "NVDA"),
    IssuerAlias("TESLA", "Tesla", "TSLA"),
    IssuerAlias("TSMC", "TSMC", "TSM"),
    IssuerAlias("TAIWAN SEMICONDUCTOR", "TSMC", "TSM"),
    IssuerAlias("BERKSHIRE", "Berkshire", "BRK-B"),
    IssuerAlias("BERKSHIRE HATHAWAY", "Berkshire", "BRK-B"),
    IssuerAlias("JPMORGAN", "JPMorgan", "JPM"),
    IssuerAlias("FUBON", "富邦金", "2881"),
    IssuerAlias("富邦金", "富邦金", "2881"),
    IssuerAlias("環球晶", "環球晶", "6488"),
    IssuerAlias("環球晶圓", "環球晶", "6488"),
    IssuerAlias("台積電", "台積電", "2330"),
    IssuerAlias("鴻海", "鴻海", "2317"),
    IssuerAlias("聯發科", "聯發科", "2454"),
)
