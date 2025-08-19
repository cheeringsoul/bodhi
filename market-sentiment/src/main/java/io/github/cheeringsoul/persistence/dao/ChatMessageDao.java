package io.github.cheeringsoul.persistence.dao;

import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.sqlobject.config.RegisterBeanMapper;
import org.jdbi.v3.sqlobject.customizer.Bind;
import org.jdbi.v3.sqlobject.customizer.BindBean;
import org.jdbi.v3.sqlobject.statement.SqlQuery;
import org.jdbi.v3.sqlobject.statement.SqlUpdate;

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

    @SqlQuery("SELECT * FROM chat_messages WHERE chat_id = :chatId ORDER BY timestamp DESC LIMIT :limit")
    List<ChatMessage> findRecentByChatId(@Bind("chatId") long chatId, @Bind("limit") int limit);
    
}
