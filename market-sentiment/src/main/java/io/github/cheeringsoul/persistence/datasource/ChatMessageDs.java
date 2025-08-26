package io.github.cheeringsoul.persistence.datasource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.github.cheeringsoul.persistence.dao.ChatMessageDao;
import io.github.cheeringsoul.persistence.pojo.ChatMessage;
import org.jdbi.v3.core.Jdbi;
import org.jdbi.v3.sqlobject.SqlObjectPlugin;

public class ChatMessageDs implements DataSource<ChatMessage> {
    static Jdbi jdbi;
    static {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("DB_URL"));
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASS"));
        HikariDataSource ds = new HikariDataSource(config);
        jdbi = Jdbi.create(ds);
    }
    Long startId;
    public ChatMessageDs(long startId) {
        this.startId = startId;
    }

    @Override
    public ChatMessage read() {
        jdbi.installPlugin(new SqlObjectPlugin());
        ChatMessageDao dao = jdbi.onDemand(ChatMessageDao.class);
        ChatMessage result = dao.findByIdGreaterThan(startId);
        if (result == null) {
            return null;
        }
        startId = result.getId();
        return result;
    }

    @Override
    public void close() {

    }
}
