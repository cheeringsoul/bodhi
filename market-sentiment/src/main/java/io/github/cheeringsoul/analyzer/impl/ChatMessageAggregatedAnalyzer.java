package io.github.cheeringsoul.analyzer.impl;

import io.github.cheeringsoul.analyzer.AggregatedAnalyzer;
import io.github.cheeringsoul.analyzer.pojo.internal.AnalysisResult;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ChatMessageAggregatedAnalyzer implements AggregatedAnalyzer<AnalysisResult, ChatMessage> {
    static private final List<String> IGNORED_MESSAGES = List.of("[picture]", "[video]", "[voice note]", "[animation]",
            "[audio]", "[sticker]", "[document]", "[location]", "[venue]", "[contact]");

    private final int intervalMinutes = 5;
    private final Map<Long, List<ChatMessage>> cachedMessages = new HashMap<>();


    @Override
    public AnalysisResult aggregate(ChatMessage data) {
        return null;
    }
}
