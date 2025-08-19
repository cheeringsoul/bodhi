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
public class ChatMessageAnalysisResult extends AnalysisResult {
    private int messageCount;
    // symbol -> count, symbol提到的次数
    private final Map<String, Integer> relatedSymbols = new HashMap<>();
    // symbol被看多看空的次数
    private final Map<String, Map<MarketSentiment, Integer>> marketSentimentCounts = new HashMap<>();
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
        marketSentimentCounts.clear();
    }

    public void copyTo(ChatMessageAnalysisResult chatMessageAnalysisResult) {
        chatMessageAnalysisResult.reset();
        chatMessageAnalysisResult.messageCount = this.messageCount;
        chatMessageAnalysisResult.relatedSymbols.putAll(this.relatedSymbols);
        chatMessageAnalysisResult.startTime = this.startTime;
        chatMessageAnalysisResult.endTime = this.endTime;
    }

}
