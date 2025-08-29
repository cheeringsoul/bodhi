package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.Bind;
import org.jdbi.v3.sqlobject.customizer.BindBean;
import org.jdbi.v3.sqlobject.statement.SqlQuery;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

import java.time.Instant;
import java.util.List;

@RegisterBeanMapper(ChatMessage.class)
public interface ChatMessageDao {
    @SqlUpdate("""
                INSERT INTO chat_messages
                (message_id, chat_id, group_name, sender_id, message_text, urls, timestamp)
                VALUES (:messageId, :chatId, :groupName, :senderId, :messageText, :urls, :timestamp)
            """)
    void insert(@BindBean ChatMessage message);

    @SqlQuery("SELECT * FROM chat_messages WHERE id = :id")
    ChatMessage findById(@Bind("id") long id);

    @SqlQuery("SELECT * FROM chat_messages WHERE id > :id order by id asc limit 1")
    ChatMessage findByIdGreaterThan(@Bind("id") long id);

    @SqlQuery("SELECT * FROM chat_messages WHERE chat_id = :chatId ORDER BY timestamp ASC LIMIT :limit")
    List<ChatMessage> findRecentByChatId(@Bind("chatId") long chatId, @Bind("limit") int limit);

    @SqlQuery("SELECT * FROM chat_messages WHERE chat_id = :chatId ORDER BY timestamp ASC LIMIT 1")
    ChatMessage findEarliestByChatId(@Bind("chatId") long chatId);

    @SqlQuery("SELECT * FROM chat_messages WHERE chat_id = :chatId AND timestamp > :timestamp ORDER BY timestamp ASC LIMIT :limit")
    List<ChatMessage> findAfterTimestamp(@Bind("chatId") long chatId, @Bind("timestamp") Instant timestamp, @Bind("limit") int limit);

    @SqlQuery("SELECT * FROM chat_messages ORDER BY timestamp ASC LIMIT 1")
    ChatMessage findEarliest();

    @SqlQuery("SELECT * FROM chat_messages WHERE timestamp > :timestamp ORDER BY timestamp ASC LIMIT :limit")
    List<ChatMessage> findAfterTimestamp( @Bind("timestamp") Instant timestamp, @Bind("limit") int limit);


}
