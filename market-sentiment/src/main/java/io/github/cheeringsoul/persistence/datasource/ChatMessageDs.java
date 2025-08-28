package io.github.cheeringsoul.persistence.datasource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.github.cheeringsoul.persistence.dao.ChatMessageDao;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.core.Jdbi;
import org.jdbi.v3.sqlobject.SqlObjectPlugin;

import java.time.Instant;
import java.util.ArrayList;
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
    }

    private Instant current;
    private final List<ChatMessage> cached = new LinkedList<>();

    @Override
    public ChatMessage read() {
        if (!cached.isEmpty()) {
            return cached.removeFirst();
        }
        long chatId = -1002463154584L;
        jdbi.installPlugin(new SqlObjectPlugin());
        ChatMessageDao dao = jdbi.onDemand(ChatMessageDao.class);
        ChatMessage start = dao.findEarliestByChatId(chatId);
        if (start == null) {
            return null;
        }
        current = start.timestamp();
        List<ChatMessage> result = dao.findAfterTimestamp(chatId, current, 1000);
        current = result.getLast().timestamp();
        cached.addAll(result);
        return result;
    }

    @Override
    public void close() {

    }
}
