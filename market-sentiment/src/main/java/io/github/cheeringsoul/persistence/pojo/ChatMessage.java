package io.github.cheeringsoul.persistence.pojo;

import lombok.*;
import org.jdbi.v3.core.mapper.reflect.ColumnName;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;

@Getter
@Setter
@ToString
public class ChatMessage extends Base {
    private long id;
    @ColumnName("message_id")
    private Long messageId;
    @ColumnName("chat_id")
    private long chatId;
    @ColumnName("group_name")
    private String groupName;
    @ColumnName("sender_id")
    private long senderId;
    @ColumnName("message_text")
    private String messageText;
    private List<String> urls;
    @Getter(AccessLevel.NONE)
    private OffsetDateTime timestamp;

    public Instant timestamp() {
        return timestamp.toInstant();
    }
}