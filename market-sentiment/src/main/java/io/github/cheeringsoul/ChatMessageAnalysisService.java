package io.github.cheeringsoul;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.github.cheeringsoul.analyzer.Analyzer;
import io.github.cheeringsoul.analyzer.impl.ChatMessageAnalyzer;
import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import io.github.cheeringsoul.persistence.dao.ChatMessageAnalysisDao;
import io.github.cheeringsoul.persistence.dao.ChatMessageDao;
import io.github.cheeringsoul.persistence.dao.MarketSentimentDao;
import io.github.cheeringsoul.persistence.dao.RelatedSymbolDao;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.core.Jdbi;
import org.jdbi.v3.sqlobject.SqlObjectPlugin;

public class ChatMessageAnalysisService {
    private final ChatMessageAnalysisDao summaryDao;
    private final RelatedSymbolDao relatedDao;
    private final MarketSentimentDao sentimentDao;
    private final Analyzer chatMessageAnalyzer;

    public ChatMessageAnalysisService(ChatMessageAnalysisDao summaryDao,
                                      RelatedSymbolDao relatedDao,
                                      MarketSentimentDao sentimentDao) {
        this.summaryDao = summaryDao;
        this.relatedDao = relatedDao;
        this.sentimentDao = sentimentDao;
        this.chatMessageAnalyzer = new ChatMessageAnalyzer(20);
    }
    public static Jdbi createJdbi() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:postgresql://localhost:5432/ymy");
        config.setUsername("ymy");
        config.setPassword("");

        HikariDataSource ds = new HikariDataSource(config);
        return Jdbi.create(ds);
    }

    public static void main(String[] args) {
        Jdbi jdbi = createJdbi();
        jdbi.installPlugin(new SqlObjectPlugin());
        ChatMessageDao dao = jdbi.onDemand(ChatMessageDao.class);
        ChatMessage result = dao.findByIdGreaterThan(1L);
        System.out.println(result);

    }

}

