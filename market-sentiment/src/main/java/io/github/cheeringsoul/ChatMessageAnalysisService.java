package io.github.cheeringsoul;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.cheeringsoul.analyzer.impl.ChatMessageAnalyzer;
import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import io.github.cheeringsoul.persistence.datasource.ChatMessageDs;
import io.github.cheeringsoul.persistence.datasource.DataSource;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;


public class ChatMessageAnalysisService {
    private final Map<Long, ChatMessageAnalyzer> chatMessageAnalyzer = new HashMap<>();


    private ChatMessageAnalyzer getChatMessageAnalyzer(long chatId) {
        return chatMessageAnalyzer.computeIfAbsent(chatId, (chatId0) -> new ChatMessageAnalyzer(20, 10));
    }

    public void run() {
        DataSource<ChatMessage> dataSource = new ChatMessageDs();
        while (true) {
            ChatMessage chatMessage = dataSource.read();
            if (chatMessage == null) {
                break;
            }
            Long chatId = chatMessage.getChatId();
            Optional<ChatMessageAnalysisResult> result = getChatMessageAnalyzer(chatId).analysis(chatMessage);
            if (result.isPresent()) {
                System.out.println(chatMessage.getGroupName() + "=====>" + result.get());
            }
        }
    }

    public static void main(String[] args) {
        ChatMessageAnalysisService service = new ChatMessageAnalysisService();
        service.run();
    }

}
