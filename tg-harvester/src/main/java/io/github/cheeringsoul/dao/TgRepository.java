package io.github.cheeringsoul.dao;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.github.cheeringsoul.pojo.ChannelNewsEntity;
import io.github.cheeringsoul.pojo.ChatMessageEntity;
import io.github.cheeringsoul.pojo.Impression;
import io.github.cheeringsoul.pojo.LinkContent;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.tuple.Pair;

import java.sql.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * @author ymy
 */
@Slf4j
public class TgRepository {
    private static final String DB_URL = System.getenv("DB_URL");
    private static final String DB_USER = System.getenv("DB_USER");
    private static final String DB_PASSWORD = System.getenv("DB_PASSWORD");
    private static final HikariDataSource DATA_SOURCE;

    static {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(DB_URL);
        config.setUsername(DB_USER);
        config.setPassword(DB_PASSWORD);
        config.setMaximumPoolSize(1);
        config.setMinimumIdle(0);
        config.setIdleTimeout(30000);
        config.setMaxLifetime(600000);
        DATA_SOURCE = new HikariDataSource(config);
    }

    public static void removeBotMessages(long chatId, long bodId) {
        String sql = "DELETE FROM chat_messages WHERE chat_id = ? AND sender_id = ?";
        try (Connection conn = DATA_SOURCE.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, chatId);
            stmt.setLong(2, bodId);
            int affectRows = stmt.executeUpdate();
            if (affectRows > 0) {
                log.info("Removed {} messages for chatId: {}, botId: {}", affectRows, chatId, bodId);
            }
        } catch (SQLException e) {
            log.error("Error removing bot messages", e);
        }
    }

    public static void insertChatMessage(ChatMessageEntity chatMessageEntity) {
        String sql = "INSERT INTO chat_messages (message_id, chat_id, group_name, sender_id, message_text, urls, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)";
        try (Connection conn = DATA_SOURCE.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, chatMessageEntity.messageId());
            stmt.setLong(2, chatMessageEntity.chatId());
            stmt.setString(3, chatMessageEntity.groupName());
            stmt.setLong(4, chatMessageEntity.senderId());
            stmt.setString(5, chatMessageEntity.messageText());
            stmt.setArray(6, conn.createArrayOf("text", chatMessageEntity.urls().toArray()));
            stmt.setTimestamp(7, Timestamp.from(chatMessageEntity.timestamp()));
            stmt.executeUpdate();
        } catch (SQLException e) {
            log.error("Error inserting message", e);
        }
    }

    public static long insertChannelNews(ChannelNewsEntity channelNewsEntity) {
        String sql = "INSERT INTO channel_news (message_id, chat_id, group_name, message_text, urls, timestamp) VALUES (?, ?, ?, ?, ?, ?)";
        try (Connection conn = DATA_SOURCE.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
            stmt.setLong(1, channelNewsEntity.messageId());
            stmt.setLong(2, channelNewsEntity.chatId());
            stmt.setString(3, channelNewsEntity.groupName());
            stmt.setString(4, channelNewsEntity.messageText());
            stmt.setArray(5, conn.createArrayOf("text", channelNewsEntity.urls().toArray()));
            stmt.setTimestamp(6, Timestamp.from(channelNewsEntity.timestamp()));
            stmt.executeUpdate();
            try (ResultSet generatedKeys = stmt.getGeneratedKeys()) {
                if (generatedKeys.next()) {
                    return generatedKeys.getLong(1);
                }
            } catch (SQLException e) {
                log.error("Error retrieving generated keys", e);
            }
        } catch (SQLException e) {
            log.error("Error inserting link data", e);
        }
        return -1;
    }

    public static void insertLinkPage(long relatedSuperGroupId, LinkContent linkContent) {
        String sql = "INSERT INTO link_content (related_super_group_id, url, title,  content, timestamp) VALUES (?, ?, ?, ?, ?)";
        try (Connection conn = DATA_SOURCE.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, relatedSuperGroupId);
            stmt.setString(2, linkContent.url());
            stmt.setString(3, linkContent.title());
            stmt.setString(4, linkContent.content());
            stmt.setTimestamp(5, Timestamp.from(linkContent.timestamp()));
            stmt.executeUpdate();
        } catch (SQLException e) {
            log.error("Error inserting link page", e);
        }
    }

    public static Pair<String, String> getConfig() {
        String sql = "select c.version, c.config  from config c order by id desc limit 1";
        try (Connection conn = DATA_SOURCE.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {
            if (rs.next()) {
                return Pair.of(rs.getString("version"), rs.getString("config"));
            }
        } catch (SQLException e) {
            log.error("Error retrieving config", e);
        }
        return null;
    }

    public static List<Pair<Integer, Long>> getConfigImpressions() {
        String sql = "select source_type, chat_id from config_impressions";
        List<Pair<Integer, Long>> list = new ArrayList<>();
        try (Connection conn = DATA_SOURCE.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql);
             ResultSet rs = stmt.executeQuery()) {
            while (rs.next()) {
                int sourceType = rs.getInt("source_type");
                if (sourceType != 0 && sourceType != 1) {
                    log.error("sourceType is not 0 or 1: {}", sourceType);
                    return List.of();
                }
                long chatId = rs.getLong("chat_id");
                list.add(Pair.of(sourceType, chatId));
            }
        } catch (SQLException e) {
            log.error("Error retrieving config impressions", e);
            return List.of();
        }
        return list;
    }

    public static void insertImpression(Impression impression) {
        String sql = "insert into impression (related_id, source_type, chat_id, group_name, views, internal, timestamp) values (?, ?, ?, ?, ?, ?, ?)";
        try (Connection conn = DATA_SOURCE.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, impression.relatedId());
            stmt.setInt(2, impression.sourceType().getValue());
            stmt.setLong(3, impression.chatId());
            stmt.setString(4, impression.groupName());
            stmt.setInt(5, impression.views());
            stmt.setString(6, impression.internal());
            stmt.setTimestamp(7, Timestamp.from(Instant.now()));
            stmt.executeUpdate();
        } catch (SQLException e) {
            log.error("Error inserting impression", e);
        }
    }
}
