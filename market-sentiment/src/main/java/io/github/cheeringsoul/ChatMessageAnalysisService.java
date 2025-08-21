package io.github.cheeringsoul;

import io.github.cheeringsoul.analyzer.pojo.ChatMessageAnalysisResult;
import io.github.cheeringsoul.persistence.dao.ChatMessageAnalysisDao;
import io.github.cheeringsoul.persistence.dao.MarketSentimentDao;
import io.github.cheeringsoul.persistence.dao.RelatedSymbolDao;

public class ChatMessageAnalysisService {
    private final ChatMessageAnalysisDao summaryDao;
    private final RelatedSymbolDao relatedDao;
    private final MarketSentimentDao sentimentDao;

    public ChatMessageAnalysisService(ChatMessageAnalysisDao summaryDao,
                                      RelatedSymbolDao relatedDao,
                                      MarketSentimentDao sentimentDao) {
        this.summaryDao = summaryDao;
        this.relatedDao = relatedDao;
        this.sentimentDao = sentimentDao;
    }

    public long save(ChatMessageAnalysisResult result) {
        long summaryId = summaryDao.insert(result);

        result.getRelatedSymbols().forEach((symbol, count) ->
                relatedDao.insert(summaryId, symbol, count));

        result.getMarketSentimentCounts().forEach((symbol, map) ->
                map.forEach((sentiment, count) ->
                        sentimentDao.insert(summaryId, symbol, sentiment.name(), count)));

        return summaryId;
    }


}

