package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.persistence.pojo.MarketSentimentCount;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.Bind;
import org.jdbi.v3.sqlobject.statement.SqlQuery;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

import java.util.List;

public interface MarketSentimentDao {
    @SqlUpdate("""
        INSERT INTO market_sentiment_count (summary_id, symbol, sentiment, count)
        VALUES (:summaryId, :symbol, :sentiment, :count)
    """)
    void insert(@Bind("summaryId") long summaryId,
                @Bind("symbol") String symbol,
                @Bind("sentiment") String sentiment,
                @Bind("count") int count);

    @SqlQuery("SELECT symbol, sentiment, count FROM market_sentiment_count WHERE summary_id = :summaryId")
    @RegisterBeanMapper(MarketSentimentCount.class)
    List<MarketSentimentCount> findBySummaryId(@Bind("summaryId") long summaryId);
}
