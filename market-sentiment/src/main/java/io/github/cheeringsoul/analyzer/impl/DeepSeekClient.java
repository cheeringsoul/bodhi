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
public class DeepSeekClient {
    private static final String API_KEY = System.getenv("DS_API_KEY");
    private static final String BASE_URL = "https://api.deepseek.com";
    private final HttpClient client;
    private final ObjectMapper mapper;

    public DeepSeekClient() {
        this.client = HttpClient.newHttpClient();
        this.mapper = new ObjectMapper();
    }

    public String askDeepSeek(String text) {
        String requestBody = """
                {
                  "model": "deepseek-chat",
                  "messages": [
                    {
                      "role": "user",
                      "content": "%s"
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
            return content;
        } catch (Exception e) {
            log.error("Error processing request to DeepSeek: {}", e.getMessage());
            return null;
        }
    }
}
