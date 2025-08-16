package io.github.cheeringsoul.pojo;

import lombok.AccessLevel;
import lombok.Getter;
import lombok.Setter;
import org.jdbi.v3.core.mapper.reflect.ColumnName;

import java.time.OffsetDateTime;
import java.util.List;

@Getter
@Setter
public class ChatMessage extends Base {
    private long id;
    @Getter(AccessLevel.NONE)
    private Long messageId;
    private long chatId;
    private String groupName;
    private long senderId;
    private String messageText;
    private List<String> urls;   // 映射 PostgreSQL TEXT[]
    private OffsetDateTime timestamp;

    @ColumnName("message_id")
    public Long getMessageId() {
        return messageId;
    }

}