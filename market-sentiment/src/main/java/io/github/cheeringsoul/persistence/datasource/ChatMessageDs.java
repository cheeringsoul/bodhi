package io.github.cheeringsoul.persistence.datasource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.github.cheeringsoul.persistence.dao.ChatMessageDao;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.core.Jdbi;
import org.jdbi.v3.sqlobject.SqlObjectPlugin;

import java.time.Instant;
import java.util.LinkedList;
import java.util.List;

public class ChatMessageDs implements DataSource<ChatMessage> {
    static private Jdbi jdbi;

    static {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("DB_URL"));
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASS"));
        HikariDataSource ds = new HikariDataSource(config);
        jdbi = Jdbi.create(ds);
        jdbi.installPlugin(new SqlObjectPlugin());
    }

    private Instant start;
    private final List<ChatMessage> cached = new LinkedList<>();

    public ChatMessageDs() {
    }

    public ChatMessageDs(Instant start) {
        this.start = start;
    }

    @Override
    public ChatMessage read() {
        if (!cached.isEmpty()) {
            return cached.removeFirst();
        }
        ChatMessageDao dao = jdbi.onDemand(ChatMessageDao.class);
        if (start == null) {
            ChatMessage chatMessage = dao.findEarliest();
            start = chatMessage.timestamp();
        }

        List<ChatMessage> result = dao.findAfterTimestamp(start, 1000);
        if (result.isEmpty()) {
            return null;
        }
        start = result.getLast().timestamp();
        cached.addAll(result);
        return cached.removeFirst();
    }

    @Override
    public void close() {

    }
}
