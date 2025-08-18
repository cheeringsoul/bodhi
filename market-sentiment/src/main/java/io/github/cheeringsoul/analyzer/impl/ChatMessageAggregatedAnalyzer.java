package io.github.cheeringsoul.analyzer.impl;

import static io.github.cheeringsoul.Utils.SymbolExtractor;
import static io.github.cheeringsoul.Utils.TimeBucket;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.cheeringsoul.Utils;
import io.github.cheeringsoul.analyzer.AggregatedAnalyzer;
import io.github.cheeringsoul.analyzer.pojo.*;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.tuple.Pair;

import java.io.IOException;
import java.io.InputStream;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
public class ChatMessageAggregatedAnalyzer implements AggregatedAnalyzer<ChatMessage, MarketActivity> {
    private static List<String> CRYPTO_TERMS;
    private static final Pattern REPEATED_PUNC_PATTERN;
    private static final Set<Character> ALLOWED_PUNCTUATION = new HashSet<>();
    private static final Set<String> IGNORED_MESSAGES = Set.of("[picture]", "[video]", "[voice note]", "[animation]",
            "[audio]", "[sticker]", "[document]", "[location]", "[venue]", "[contact]");

    static {
        // load crypto terms from JSON file
        var mapper = new ObjectMapper();
        try (InputStream inputStream = ChatMessageAggregatedAnalyzer.class.getClassLoader().getResourceAsStream("crypto_terms.json")) {
            CRYPTO_TERMS = mapper.readValue(inputStream, new TypeReference<>() {
            });
            if (CRYPTO_TERMS.isEmpty()) {
                throw new RuntimeException("crypto_terms.json is empty.");
            }
        } catch (IOException e) {
            log.error("crypto_terms.json load failed.", e);
        }

        for (char c : ".,!?;:。，？！".toCharArray()) {
            ALLOWED_PUNCTUATION.add(c);
        }
        var allowedRegex = "[\\.,!\\?;:。，？！]";
        REPEATED_PUNC_PATTERN = Pattern.compile("(" + allowedRegex + ")\\1+");
    }

    private int intervalMinutes;
    private int windowSize = 10;

    private final DeepSeekClient deepSeekClient;
    private final List<SimpleChatMessage> cachedMessages = new ArrayList<>();
    private final MarketActivity marketActivity = new MarketActivity();
    private final MarketActivity result = new MarketActivity();
    private final OllamaClient ollamaClient;

    public ChatMessageAggregatedAnalyzer(int intervalMinutes) {
        this.intervalMinutes = intervalMinutes;
        ollamaClient = new OllamaClient("deepseek-r1:1.5b");
        deepSeekClient = new DeepSeekClient();
    }

    @Override
    public Optional<MarketActivity> aggregate(ChatMessage data) {
        var shouldYield = false;
        if (marketActivity.endTime() != null && TimeBucket.isSameBucket(data.timestamp(), marketActivity.endTime(), intervalMinutes)) {
            // todo get market sentiment
            cachedMessages.clear();
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
            addMessage(new SimpleChatMessage(data.senderId(), data.messageText()));
        }
        if (shouldYield) {
            return Optional.of(result);
        }
        return Optional.empty();
    }

    private void addMessage(SimpleChatMessage message) {
        if (cachedMessages.isEmpty()) {
            cachedMessages.add(message);
        } else {
            var lastMessage = cachedMessages.getLast();
            if (Objects.equals(lastMessage.sender(), message.sender())) {
                // merge with last message
                cachedMessages.set(cachedMessages.size() - 1, new SimpleChatMessage(message.sender(), lastMessage.text() + " " + message.text()));
            } else {
                cachedMessages.add(message);
            }
        }
    }

    private String cleanText(String text) {
        if (text == null || text.isEmpty()) {
            return "";
        }
        // 1. 替换连续重复的允许标点为一个
        Matcher matcher = REPEATED_PUNC_PATTERN.matcher(text);
        text = matcher.replaceAll("$1");
        // 2. 去掉非字母、非数字、非空格、非允许标点的字符
        StringBuilder sb = new StringBuilder();
        for (char c : text.toCharArray()) {
            if (Character.isLetterOrDigit(c) || Character.isWhitespace(c) || ALLOWED_PUNCTUATION.contains(c)) {
                sb.append(c);
            }
        }
        text = sb.toString();
        // 3. 去掉多余空格和换行
        text = text.replaceAll("\\s+", " ").trim();
        // 4. 去掉所有空格
        text = text.replace(" ", "");
        return text;
    }

    private Pair<String, IsFinancialRelated> preProcess(String text) {
        if (text == null || text.isEmpty()) {
            return Pair.of("", IsFinancialRelated.NOT_FINANCIAL);
        }
        String cleanedText = cleanText(text);
        if (cleanedText.isEmpty()) {
            return Pair.of("", IsFinancialRelated.NOT_FINANCIAL);
        }
        boolean isFinancial = CRYPTO_TERMS.stream().anyMatch(cleanedText::contains);
        if (isFinancial) {
            return Pair.of(text, IsFinancialRelated.FINANCIAL);
        }
        return Pair.of(text, IsFinancialRelated.UNKNOWN);
    }

    private Pair<String, IsFinancialRelated> askOllama(String text) {
        return Pair.of(text, ollamaClient.process(text));
    }

    private Pair<Set<String>, List<SimpleChatMessage>> findWithContext(List<SimpleChatMessage> messages, int n) {
        List<SimpleChatMessage> result = new ArrayList<>();
        List<String> relatedSymbols = new ArrayList<>();
        for (int i = 0; i < messages.size(); i++) {
            SimpleChatMessage item = messages.get(i);
            var symbols = Utils.SymbolExtractor.INSTANCE.extractCrypto(item.text());
            relatedSymbols.addAll(symbols);
            if (!symbols.isEmpty()) {
                int start = Math.max(0, i - n);
                int end = Math.min(messages.size(), i + n + 1);
                result.addAll(messages.subList(start, end));
            }
        }
        Set<String> set = new HashSet<>(relatedSymbols);
        return Pair.of(set, result);
    }

    private Map<String, Map<MarketSentiment, Integer>> analyze(List<SimpleChatMessage> messages) {
        if (messages.isEmpty()) {
            return Collections.emptyMap();
        }
        Iterator<SimpleChatMessage> iterator = cachedMessages.iterator();
        while (iterator.hasNext()) {
            SimpleChatMessage item = iterator.next();
            String newItem = cleanText(item.text());
            if (newItem.isEmpty()) {
                iterator.remove();
            } else {
                item.text(newItem);
            }
        }
        Pair<Set<String>, List<SimpleChatMessage>> pair = findWithContext(cachedMessages, windowSize);
        Set<String> symbols = pair.getLeft();
        List<SimpleChatMessage> contextMessages = pair.getRight();
        // todo
        deepSeekClient.askDeepSeek(generatePrompt(symbols, contextMessages));
    }

    private String generatePrompt(Set<String> symbols, List<SimpleChatMessage> messages) {
        StringBuilder sb = new StringBuilder();
        sb.append("Analyze the following messages and determine the market sentiment for the mentioned symbols:\n");
        sb.append("Symbols: ").append(String.join(", ", symbols)).append("\n\n");
        for (SimpleChatMessage message : messages) {
            sb.append(message.sender()).append(": ").append(message.text()).append("\n");
        }
        sb.append("\nPlease provide a sentiment analysis for each symbol, indicating whether it is bullish, bearish, or neutral.");
        return sb.toString();
    }
}















