package io.github.cheeringsoul;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.github.cheeringsoul.dao.TgRepository;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.tuple.Pair;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;


@Slf4j
@ToString
public class Config {
    private final Map<Long, String> superGroupNameMap = new HashMap<>();
    private final Map<Long, String> newsChannelNameMap = new HashMap<>();

    private volatile List<Long> ignoredChatIds;
    private volatile String version;

    private volatile Map<String, ParseConfig> parseConfig;

    public Config(Map<String, ParseConfig> parseConfig, List<Long> ignoredChatIds, String version) {
        this.parseConfig = parseConfig;
        this.ignoredChatIds = new ArrayList<>(ignoredChatIds);
        this.version = version;
    }

    @Setter
    @Getter
    public static class ParseConfig {
        @com.fasterxml.jackson.annotation.JsonProperty("default_parser")
        private String defaultParser;
        @com.fasterxml.jackson.annotation.JsonProperty("ignore_bot")
        private BotFilter ignoreBot;
        @com.fasterxml.jackson.annotation.JsonProperty("extract_link")
        private LinkFilter extractLink;
    }

    @Getter
    public static class BotFilter {
        private boolean default_;
        @Setter
        private List<Long> exclude;

        @com.fasterxml.jackson.annotation.JsonProperty("default")
        public void setDefault_(boolean default_) {
            this.default_ = default_;
        }

    }

    @Getter
    public static class LinkFilter {
        private boolean default_;
        @Setter
        private List<Long> include;

        @com.fasterxml.jackson.annotation.JsonProperty("default")
        public void setDefault_(boolean default_) {
            this.default_ = default_;
        }

    }

    public void addSuperGroup(long chatId, String superGroupName) {
        if (superGroupNameMap.containsKey(chatId)) {
            log.warn("Super group with chatId {} already exists, updating name from {} to {}", chatId, superGroupNameMap.get(chatId), superGroupName);
        }
        superGroupNameMap.put(chatId, superGroupName);
    }

    public void addNewsChannel(long chatId, String newsChannelName) {
        if (newsChannelNameMap.containsKey(chatId)) {
            log.warn("News channel with chatId {} already exists, updating name from {} to {}", chatId, newsChannelNameMap.get(chatId), newsChannelName);
        }
        newsChannelNameMap.put(chatId, newsChannelName);
    }

    public String getSuperGroupName(long chatId) {
        return superGroupNameMap.get(chatId);
    }

    public String getNewsChannelName(long chatId) {
        return newsChannelNameMap.get(chatId);
    }

    public String getGroupName(long chatId) {
        String groupName;
        if ((groupName = getSuperGroupName(chatId)) != null || (groupName = getNewsChannelName(chatId)) != null) {
            return groupName;
        }
        return "Unknown Group";
    }

    public boolean containsChatId(long chatId) {
        return superGroupNameMap.containsKey(chatId) || newsChannelNameMap.containsKey(chatId);
    }

    public boolean isNewsChannel(long chatId) {
        return newsChannelNameMap.containsKey(chatId);
    }

    public boolean isSuperGroup(long chatId) {
        return superGroupNameMap.containsKey(chatId);
    }

    public String getParserName(long chatId) {
        if (isNewsChannel(chatId)) {
            return parseConfig.get("news_channel").getDefaultParser();
        }
        if (superGroupNameMap.containsKey(chatId)) {
            return parseConfig.get("super_group").getDefaultParser();
        }
        return null;
    }

    public boolean needExtractLink(long chatId) {
        if (!isNewsChannel(chatId)) {
            return false;
        }
        LinkFilter linkFilter = parseConfig.get("news_channel").getExtractLink();
        if (linkFilter.getInclude().contains(chatId)) {
            return true;
        }
        return linkFilter.isDefault_();
    }

    public boolean ignoreBot(long chatId) {
        if (!isSuperGroup(chatId)) {
            return false;
        }
        BotFilter botFilter = parseConfig.get("super_group").getIgnoreBot();
        if (botFilter.getExclude().contains(chatId)) {
            return false;
        }
        return botFilter.isDefault_();
    }

    public boolean isIgnoredChat(long chatId) {
        return ignoredChatIds.contains(chatId);
    }

    public static Config loadFromJson() {

        try (InputStream inputStream = Config.class.getClassLoader().getResourceAsStream("config.json")) {
            if (inputStream == null) {
                throw new RuntimeException("config.json not found");
            }
            var sb = new StringBuilder();
            try (var reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line).append("\n");
                }
            }
            var config = parse(sb.toString());
            log.info("load config form json: {}", config);
            return config;
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    private static Config parse(String json) {
        if (json == null) {
            log.error("config json is null");
            return null;
        }
        ObjectMapper mapper = new ObjectMapper();
        JsonNode root;
        try {
            root = mapper.readTree(json);
        } catch (JsonProcessingException e) {
            log.error("config json parse error", e);
            return null;
        }
        String version = root.get("version").asText();
        List<Long> ignoredChats = new ArrayList<>();
        JsonNode ignoredNode = root.get("ignored_chats");
        if (ignoredNode != null && ignoredNode.isArray()) {
            for (JsonNode idNode : ignoredNode) {
                ignoredChats.add(idNode.asLong());
            }
        }
        ObjectNode filtered = mapper.createObjectNode();
        root.fields().forEachRemaining(entry -> {
            String key = entry.getKey();
            if (!"ignored_chats".equals(key) && !"version".equals(key)) {
                filtered.set(key, entry.getValue());
            }
        });
        Map<String, ParseConfig> config = mapper.convertValue(filtered,
                mapper.getTypeFactory().constructMapType(Map.class, String.class, ParseConfig.class));
        return new Config(config, ignoredChats, version);
    }

    public static Config loadFromDb() {
        Pair<String, String> configPair = TgRepository.getConfig();
        if (configPair == null) {
            log.error("config from db is null");
            return null;
        }
        String version = configPair.getLeft();
        Config config = parse(configPair.getRight());
        if (config == null) {
            log.error("Failed to parse configuration from the database.");
            return null;
        }
        if (!version.equals(config.version)) {
            log.error("version of configuration from database mismatch.");
            return null;
        }
        log.info("load config from db: {}", config);
        return config;
    }

    public void updateConfig(Config newConfig) {
        if (newConfig.version.equals(this.version)) {
            return;
        }
        this.version = newConfig.version;
        this.parseConfig = newConfig.parseConfig;
        this.ignoredChatIds.clear();
        this.ignoredChatIds = new ArrayList<>(newConfig.ignoredChatIds);
    }

}

