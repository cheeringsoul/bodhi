package io.github.cheeringsoul.analyzer.impl;

import static io.github.cheeringsoul.Utils.SymbolExtractor;
import static io.github.cheeringsoul.Utils.TimeBucket;

import io.github.cheeringsoul.analyzer.AggregatedAnalyzer;
import io.github.cheeringsoul.analyzer.pojo.MarketActivity;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;

import java.util.*;

public class ChatMessageAggregatedAnalyzer implements AggregatedAnalyzer<ChatMessage, MarketActivity> {
    static private final Set<String> IGNORED_MESSAGES = Set.of("[picture]", "[video]", "[voice note]", "[animation]",
            "[audio]", "[sticker]", "[document]", "[location]", "[venue]", "[contact]");

    private int intervalMinutes;
    private final MarketActivity marketActivity = new MarketActivity();
    private final MarketActivity result = new MarketActivity();

    static class ChatMessageContainer {
        private final Map<Long, String> messagesBySender = new LinkedHashMap<>();

        void addMessage(Long senderId, String text) {
            messagesBySender.put(senderId, text);
        }

    }

    private final ChatMessageContainer cachedMessages = new ChatMessageContainer();

    public ChatMessageAggregatedAnalyzer(int intervalMinutes) {
        this.intervalMinutes = intervalMinutes;
    }

    @Override
    public Optional<MarketActivity> aggregate(ChatMessage data) {
        var shouldYield = false;
        if (marketActivity.endTime() != null && TimeBucket.isSameBucket(data.timestamp(), marketActivity.endTime(), intervalMinutes)) {
            // todo get market sentiment
            marketActivity.putMarketSentiment(Map.of());
            marketActivity.copyTo(result);
            marketActivity.reset();
            shouldYield = true;
        }
        if (marketActivity.startTime() == null) {
            marketActivity.startTime(data.timestamp());
        }
        marketActivity.endTime(data.timestamp());
        marketActivity.incrementMessageCount();
        if (!Objects.equals(data.messageText(), "") && !IGNORED_MESSAGES.contains(data.messageText())) {
            List<String> symbols = SymbolExtractor.INSTANCE.extractCrypto(data.messageText());
            for (var symbol : symbols) {
                marketActivity.relatedSymbols().merge(symbol, 1, Integer::sum);
            }
            cachedMessages.addMessage(data.senderId(), data.messageText());
        }
        if (shouldYield) {
            return Optional.of(result);
        }
        return Optional.empty();
    }

}















