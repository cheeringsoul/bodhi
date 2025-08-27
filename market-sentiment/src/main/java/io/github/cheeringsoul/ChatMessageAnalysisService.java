package io.github.cheeringsoul;

import com.zaxxer.hikari.HikariDataSource;
import io.github.cheeringsoul.analyzer.Analyzer;
import io.github.cheeringsoul.analyzer.impl.ChatMessageAnalyzer;
import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import io.github.cheeringsoul.persistence.dao.ChatMessageAnalysisDao;
import io.github.cheeringsoul.persistence.dao.ChatMessageDao;
import io.github.cheeringsoul.persistence.dao.MarketSentimentDao;
import io.github.cheeringsoul.persistence.dao.RelatedSymbolDao;
import io.github.cheeringsoul.persistence.datasource.ChatMessageDs;
import io.github.cheeringsoul.persistence.datasource.DataSource;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.core.Jdbi;
import org.jdbi.v3.sqlobject.SqlObjectPlugin;

import java.util.Optional;


public class ChatMessageAnalysisService {
//    private final ChatMessageAnalysisDao summaryDao;
//    private final RelatedSymbolDao relatedDao;
//    private final MarketSentimentDao sentimentDao;
    private final ChatMessageAnalyzer chatMessageAnalyzer;

    public ChatMessageAnalysisService() {
//        this.summaryDao = summaryDao;
//        this.relatedDao = relatedDao;
//        this.sentimentDao = sentimentDao;
        this.chatMessageAnalyzer = new ChatMessageAnalyzer(20, 10);
    }

    public void run() {
        DataSource<ChatMessage> dataSource = new ChatMessageDs(0);
        while (true) {
            ChatMessage chatMessage = dataSource.read();
            if (chatMessage == null) {
                break;
            }
            System.out.println(chatMessage.timestamp());
//            Optional<ChatMessageAnalysisResult> result = chatMessageAnalyzer.analysis(chatMessage);
//            if (result.isPresent()) {
//                System.out.println(result.get());
//            }
        }
    }

    public static void main(String[] args) {
        ChatMessageAnalysisService service = new ChatMessageAnalysisService();
        service.run();
    }

}
