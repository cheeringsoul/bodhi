package io.github.cheeringsoul.analyzer.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.cheeringsoul.analyzer.pojo.MarketSentiment;
import lombok.extern.slf4j.Slf4j;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

@Slf4j
public class DsClient {
    private static final String API_KEY = System.getenv("DS_API_KEY");
    private static final String BASE_URL = "https://api.deepseek.com";
    private final HttpClient client;
    private final ObjectMapper mapper;

    public DsClient() {
        this.client = HttpClient.newHttpClient();
        this.mapper = new ObjectMapper();
    }

    public MarketSentiment analyze(String text) {
        String requestBody = """
                {
                  "model": "deepseek-chat",
                  "messages": [
                    {
                      "role": "user",
                      "content": "\\"%s\\"，上面这段话来自加密货币聊天群，你认为它反应了散户当前短期是看空还是看多的？你只需要回答我是看多还是看空，不要解释原因"
                    }
                  ],
                  "stream": false
                }
                """.formatted(text);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL))
                .header("Authorization", "Bearer " + API_KEY)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(requestBody))
                .build();
        try{
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode root = mapper.readTree(response.body());
            String content = root.path("choices").get(0).path("message").path("content").asText();
            log.info("ask deepseek: {}, response: {}", text, content);
            if ("看多".equals(content)) {
                return MarketSentiment.BULLISH;
            } else if ("看空".equals(content)) {
                return MarketSentiment.BEARISH;
            } else {
                return MarketSentiment.NEUTRAL;
            }
        } catch (Exception e) {
            log.error("Error processing request to DeepSeek: {}", e.getMessage());
            return null;
        }
    }
}
