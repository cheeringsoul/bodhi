package io.github.cheeringsoul;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Utils {

    public static class TimeBucket {
        public static boolean isSameBucket(Instant t1, Instant t2, int intervalMinutes) {
            var zone = ZoneId.systemDefault();
            LocalDateTime ldt1 = LocalDateTime.ofInstant(t1, zone);
            LocalDateTime ldt2 = LocalDateTime.ofInstant(t2, zone);

            int minutes1 = ldt1.getHour() * 60 + ldt1.getMinute();
            int minutes2 = ldt2.getHour() * 60 + ldt2.getMinute();

            int bucket1 = minutes1 / intervalMinutes;
            int bucket2 = minutes2 / intervalMinutes;

            return ldt1.toLocalDate().equals(ldt2.toLocalDate()) && bucket1 == bucket2;
        }
    }

    public static class CoinMarketCapApi {
        private static final String API_KEY = System.getenv("COIN_MARKET_CAP_API_KEY");
        private static final String URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest";

        private final HttpClient client;
        private final ObjectMapper mapper;

        public CoinMarketCapApi() {
            this.client = HttpClient.newHttpClient();
            this.mapper = new ObjectMapper();
        }

        public List<Map<String, String>> getSymbols() throws IOException, InterruptedException {
            String parameters = "start=1&limit=800&convert=USD";

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(URL + "?" + parameters))
                    .header("Accepts", "application/json")
                    .header("X-CMC_PRO_API_KEY", API_KEY)
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode root = mapper.readTree(response.body());
            List<Map<String, String>> result = new ArrayList<>();
            if (root.path("status").path("error_code").asInt() == 0) {
                for (JsonNode each : root.path("data")) {
                    Map<String, String> map = new HashMap<>();
                    map.put("name", each.path("name").asText().toLowerCase());
                    map.put("symbol", each.path("symbol").asText());
                    result.add(map);
                }
            }
            return result;
        }
    }

    public enum SymbolExtractor {
        INSTANCE;

        private final Set<String> cryptoNames = new HashSet<>();
        private final Set<String> cryptoSymbols = new HashSet<>();
        private List<Map<String, String>> symbols = null;

        public List<String> extractCrypto(String text) {
            if (symbols == null) {
                symbols = getSymbols();
                updateSymbols(symbols);
            }

            List<String> results = new ArrayList<>();

            // 1. 匹配所有英文单词（长度 2~12 避免单字母干扰）
            Pattern wordPattern = Pattern.compile("[A-Za-z]{2,12}");
            Matcher wordMatcher = wordPattern.matcher(text);
            while (wordMatcher.find()) {
                String word = wordMatcher.group();
                String lw = word.toLowerCase();
                if (cryptoNames.contains(lw) || cryptoSymbols.contains(lw)) {
                    results.add(word);
                }
            }
            // 2. 其他几种模式
            String[] patterns = {
                    "\\$[A-Za-z]{2,10}",
                    "[A-Za-z]{2,10}/[A-Za-z]{2,10}",
                    "#[A-Za-z]{2,10}"
            };
            for (String regex : patterns) {
                Pattern pattern = Pattern.compile(regex);
                Matcher matcher = pattern.matcher(text);
                while (matcher.find()) {
                    String match = matcher.group();
                    String token = match.replaceAll("[^A-Za-z]", "");
                    if (cryptoSymbols.contains(token.toLowerCase())) {
                        results.add(token.toUpperCase());
                    }
                }
            }
            return results;
        }

        private List<Map<String, String>> getSymbols() {
            CoinMarketCapApi api = new CoinMarketCapApi();
            try {
                return api.getSymbols();
            } catch (IOException | InterruptedException e) {
                throw new RuntimeException(e);
            }
        }

        public void updateSymbols(List<Map<String, String>> symbols) {
            this.symbols = symbols;
            this.cryptoNames.clear();
            this.cryptoSymbols.clear();
            for (Map<String, String> symbol : symbols) {
                this.cryptoNames.add(symbol.get("name").toLowerCase());
                this.cryptoSymbols.add(symbol.get("symbol").toLowerCase());
            }
        }
    }
}
