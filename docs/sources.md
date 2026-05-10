# Source Inventory

## Financial Data

- SEC `company_tickers.json`
- SEC `submissions`
- SEC `companyfacts`
- SEC filing archive documents
- TWSE OpenAPI
- MOPS API
- TPEX company page / finance-report endpoints

## Macro / Policy

- Federal Reserve press & speeches
- BLS latest releases
- FRED Blog
- BIS speeches / statistics / press
- ECB press
- Liberty Street Economics
- St. Louis Fed On the Economy
- NIST Cybersecurity Insights
- CSET

## Industry / Company

- NVIDIA Newsroom
- Apple Newsroom
- Microsoft Blog
- Google Blog / Google AI Blog
- Intel Newsroom
- OpenAI News
- DeepMind Blog
- Hugging Face Blog
- SemiAnalysis
- Semiconductor Engineering
- Semiconductor Digest
- 3D InCites
- TrendForce
- DIGITIMES
- Cloudflare Blog
- Google Research
- Ollama Releases
- vLLM Releases
- openai-python Releases
- Asterisk

## Social / Feed Tooling

- RSSHub self-hosted X user feeds
- Local RSSHub docker compose bootstrap for launchd runs
- changedetection.io for non-RSS official pages / PDF / JSON changes
- GitHubTrendingRSS
- awesome-rsshub-routes feed directory
- awesome-rss-feeds directory

## Notes

- 只保留免費、可重複抓取、且內容密度足夠的來源
- 已知長期不穩定來源會直接停用，而不是讓 pipeline 每次浪費重試
- X 類來源優先走 RSSHub 這類可自架 feed bridge，不直接依賴付費官方 API
