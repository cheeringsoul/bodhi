package io.github.cheeringsoul.analyzer.pojo;

import lombok.Getter;
import lombok.Setter;
import lombok.experimental.Accessors;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@Getter
@Setter
@Accessors(fluent = true)
public class MarketActivity extends AnalysisResult {
    private int messageCount;
    // symbol -> count
    private final Map<String, Integer> relatedSymbols = new HashMap<>();
    // senderId -> MarketSentiment
    private final Map<Long, MarketSentiment> marketSentiments = new HashMap<>();
    private Instant startTime;
    private Instant endTime;

    public void incrementMessageCount() {
        messageCount++;
    }

    public void reset() {
        startTime = null;
        endTime = null;
        messageCount = 0;
        relatedSymbols.clear();
        marketSentiments.clear();
    }

    public void putMarketSentiment(Map<Long, MarketSentiment> marketSentiments) {
        this.marketSentiments.putAll(marketSentiments);
    }

    public void copyTo(MarketActivity marketActivity) {
        marketActivity.reset();
        marketActivity.messageCount = this.messageCount;
        marketActivity.relatedSymbols.putAll(this.relatedSymbols);
        marketActivity.marketSentiments.putAll(this.marketSentiments);
        marketActivity.startTime = this.startTime;
        marketActivity.endTime = this.endTime;
    }

}
