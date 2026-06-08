# Provider Matrix

| Domain | Primary sources | Fallback | Status | Env | Freshness |
|---|---|---|---|---|---|
| flights | Amadeus, Skyscanner | mock | live-ready boundary | `AMADEUS_CLIENT_ID`, `SKYSCANNER_API_KEY` | short TTL, reprice before booking |
| accommodations | Expedia Rapid, Hotelbeds, Booking Demand, Agoda Partner, Google Hotels Partner | mock | live-ready boundary; Airbnb public pages disabled until explicit authorization | provider credentials | short TTL, recheck before booking |
| places | Google Places, Kakao Local, KTO TourAPI | mock | live-ready boundary | maps/local API keys | medium TTL |
| routes | Google Routes, Naver Directions, Kakao Mobility | mock | live-ready boundary | maps/mobility API keys | medium/short TTL |
| activities | Viator, GetYourGuide | mock | partner access required | partner API keys | medium TTL |
| visa | Sherpa, Timatic | mock | partner access required | visa API keys | official verification required |
| safety | MOFA | mock | live-ready boundary | `MOFA_API_KEY` | official verification required |
| weather | Open-Meteo, OpenWeather | mock | Open-Meteo enabled by default policy | weather API keys | short TTL |
| fx | Frankfurter, Open Exchange Rates | mock | Frankfurter enabled by default policy | FX API keys | medium TTL |

Mock sources remain dev/test/fallback only and must not be presented as live data.
