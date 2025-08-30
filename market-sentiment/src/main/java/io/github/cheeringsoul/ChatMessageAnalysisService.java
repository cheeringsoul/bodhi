package io.github.cheeringsoul;

import io.github.cheeringsoul.analyzer.impl.ChatMessageAnalyzer;
import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import io.github.cheeringsoul.persistence.datasource.ChatMessageDs;
import io.github.cheeringsoul.persistence.datasource.DataSource;
import io.github.cheeringsoul.persistence.datasource.MessageSummaryDs;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import io.github.cheeringsoul.persistence.pojo.MessageSummary;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;


public class ChatMessageAnalysisService {
    private final Map<Long, ChatMessageAnalyzer> chatMessageAnalyzer = new HashMap<>();


    private ChatMessageAnalyzer getChatMessageAnalyzer(long chatId) {
        return chatMessageAnalyzer.computeIfAbsent(chatId, (chatId0) -> new ChatMessageAnalyzer(chatId0, 20, 10));
    }

    public void run() {
        DataSource<ChatMessage> dataSource = new ChatMessageDs(JdbiSupplier.supplier());
        DataSource<MessageSummary> messageSummaryDs = new MessageSummaryDs(JdbiSupplier.supplier());

        while (true) {
            ChatMessage chatMessage = dataSource.read();
            if (chatMessage == null) {
                break;
            }
            long chatId = chatMessage.getChatId();
            Optional<ChatMessageAnalysisResult> result = getChatMessageAnalyzer(chatId).analysis(chatMessage);
            if (result.isPresent()) {
//                System.out.println(chatMessage.getGroupName() + "=====>" + result.get());
                var messageSummary = result.get().getMessageSummary();
                System.out.println(messageSummary);
                messageSummaryDs.save(messageSummary);
            }
        }
    }

    public static void main(String[] args) {
        ChatMessageAnalysisService service = new ChatMessageAnalysisService();
        service.run();
    }

}
