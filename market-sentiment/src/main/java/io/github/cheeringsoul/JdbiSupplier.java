package io.github.cheeringsoul;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.jdbi.v3.core.Jdbi;
import org.jdbi.v3.sqlobject.SqlObjectPlugin;

import java.util.function.Supplier;

public class JdbiSupplier {
    private static final Jdbi jdbi;

    static {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("DB_URL"));
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASS"));
        HikariDataSource ds = new HikariDataSource(config);
        jdbi = Jdbi.create(ds);
        jdbi.installPlugin(new SqlObjectPlugin());
    }

    public static Supplier<Jdbi> supplier() {
        return () -> jdbi;
    }
}
