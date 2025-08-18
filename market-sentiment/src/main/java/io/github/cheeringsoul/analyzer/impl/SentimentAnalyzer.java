package io.github.cheeringsoul.analyzer.impl;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.cheeringsoul.Utils;
import io.github.cheeringsoul.analyzer.pojo.IsFinancialRelated;
import io.github.cheeringsoul.analyzer.pojo.MarketSentiment;
import io.github.cheeringsoul.analyzer.pojo.SimpleChatMessage;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.tuple.Pair;

import java.io.*;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
public class SentimentAnalyzer {
    private static List<String> CRYPTO_TERMS;
    private static final Pattern REPEATED_PUNC_PATTERN;
    private static final Set<Character> ALLOWED_PUNCTUATION = new HashSet<>();

    static {
        // load crypto terms from JSON file
        var mapper = new ObjectMapper();
        try (InputStream inputStream = SentimentAnalyzer.class.getClassLoader().getResourceAsStream("crypto_terms.json")) {
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

    private int windowSize = 10;
    private final DsClient dsClient;
    private final OllamaClient ollamaClient;
    private final List<SimpleChatMessage> lastMessages = new ArrayList<>();

    public SentimentAnalyzer(String model) {
        ollamaClient = new OllamaClient(model);
        dsClient = new DsClient();
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

    public Pair<Set<String>, List<SimpleChatMessage>> findWithContext(List<SimpleChatMessage> messages, int n) {
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

    public Map<MarketSentiment, Integer> analyze(List<SimpleChatMessage> messages) {
        Iterator<SimpleChatMessage> iterator = messages.iterator();
        while (iterator.hasNext()) {
            SimpleChatMessage item = iterator.next();
            String newItem = cleanText(item.text());
            if (newItem.isEmpty()) {
                iterator.remove();
            } else {
                item.text(newItem);
            }
        }
        if (messages.isEmpty()) {
            return Collections.emptyMap();
        }
        Pair<Set<String>, List<SimpleChatMessage>> pair = findWithContext(messages, windowSize);
        Set<String> symbols = pair.getLeft();
        List<SimpleChatMessage> contextMessages = pair.getRight();
    }
}
