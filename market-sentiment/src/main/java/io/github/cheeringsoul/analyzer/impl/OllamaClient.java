package io.github.cheeringsoul.analyzer.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.cheeringsoul.analyzer.pojo.IsFinancialRelated;
import lombok.extern.slf4j.Slf4j;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

@Slf4j
public class OllamaClient {

    private final String url;
    private final String model;
    private final HttpClient client;
    private final ObjectMapper mapper = new ObjectMapper();

    public OllamaClient(String model) {
        this.url = System.getenv("OLLAMA_URL");
        this.model = model;
        this.client = HttpClient.newHttpClient();
    }

    public IsFinancialRelated process(String text) {
        String prompt = String.format("\"%s\"，判断这句话是不是\"金融领域相关\"或者与\"加密货币、价格、趋势、经济\"相关，你只需要回答我\"是\"或\"不是\"不要解释原因", text);
        try {
            // 构建 JSON payload
            String jsonPayload = mapper.createObjectNode()
                    .put("model", model)
                    .put("prompt", prompt)
                    .put("stream", false)
                    .toString();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonPayload))
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode data = mapper.readTree(response.body());
            String answer = data.get("response").asText();

            if ("是".equals(answer)) {
                return IsFinancialRelated.FINANCIAL;
            } else if ("不是".equals(answer)) {
                return IsFinancialRelated.NOT_FINANCIAL;
            } else {
                log.error("Unexpected response from Ollama, ask: {}, answer: {}", prompt, data);
                return IsFinancialRelated.UNKNOWN;
            }
        } catch (IOException | InterruptedException e) {
            log.error(e.getMessage());
            return IsFinancialRelated.UNKNOWN;
        }
    }
}