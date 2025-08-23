package io.github.cheeringsoul;

import io.github.cheeringsoul.dao.TgRepository;
import io.github.cheeringsoul.parser.ParserFactory;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.drinkless.tdlib.*;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.BiConsumer;
import java.util.function.Consumer;

/**
 * @author ymy
 */
@Slf4j
public class TelegramReceiver {
    private final Client client;
    private final Config config = Config.loadFromJson();
    private final BotConfig botConfig = new BotConfig();
    private final Map<String, List<String>> readableBotIdMap = new ConcurrentHashMap<>();
    private final ParserFactory parserParserFactory = new ParserFactory(config, botConfig::isBotId);
    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);

    public TelegramReceiver() {
        client = Client.create(new TdClientHandler(), e -> log.error("tdlib error: ", e), e -> log.error("tdlib exception: ", e));
    }

    private static class BotConfig {
        @Getter
        private final Map<Long, Set<Long>> botIdMap = new ConcurrentHashMap<>();

        public void addBotId(long chatId, long botId) {
            botIdMap.computeIfAbsent(chatId, k -> ConcurrentHashMap.newKeySet()).add(botId);
        }

        public boolean isBotId(long chatId, long senderId) {
            return botIdMap.getOrDefault(chatId, Set.of()).contains(senderId);
        }

    }

    public void removeBotMessages() {
        botConfig.botIdMap.forEach((chatId, botIds) -> botIds.forEach(botId -> TgRepository.removeBotMessages(chatId, botId)));
    }


    public TelegramReceiver setProxy(Client client) {
        if (System.getenv("PROXY_HOST") == null) {
            return this;
        }
        TdApi.ProxyType proxyType = new TdApi.ProxyTypeSocks5("", "");
        TdApi.AddProxy addProxyRequest = new TdApi.AddProxy(System.getenv("PROXY_HOST"), Integer.parseInt(System.getenv("PROXY_PORT")), true, proxyType);
        client.send(addProxyRequest, result -> {
            if (result instanceof TdApi.Proxy proxy) {
                log.info("代理添加成功");
                int proxyId = proxy.id;
                TdApi.EnableProxy enableProxyRequest = new TdApi.EnableProxy(proxyId);
                client.send(enableProxyRequest, result1 -> {
                    if (result1 instanceof TdApi.Ok) {
                        log.info("代理设置成功");
                    }
                });
            } else {
                log.error("代理添加失败：{}", result);
            }
        });
        return this;
    }

    /**
     * @param level 0	关闭日志	不打印任何日志信息
     *              1	严重错误	仅显示 严重错误（Fatal Errors）
     *              2	错误	仅显示 错误（Errors）
     *              3	警告	仅显示 警告（Warnings） 和更高级别的错误
     *              4	信息	显示 信息（Info） 级别及以上的日志
     *              5	调试（默认）	默认级别，显示调试信息和所有重要事件
     *              >= 6	详细调试	更多详细的调试信息，级别越高，日志越多
     */
    public void setLogLevels(int level) {
        client.send(new TdApi.SetLogVerbosityLevel(level), result -> {
            if (result instanceof TdApi.Ok) {
                log.info("TDLib logging disabled successfully.");
            } else {
                log.error("Failed to disable TDLib logging: {}", result);
            }
        });
        log.info("TDLib logging level set to {}", level);
    }

    class TdClientHandler implements Client.ResultHandler {
        private final Scanner scanner = new Scanner(System.in);

        public void handleMessage(TdApi.Object object) {

            if (object instanceof TdApi.UpdateNewMessage update) {
                TdApi.Message message = update.message;
                if (config.isIgnoredChat(message.chatId)) {
                    return;
                }
                try{
                    parserParserFactory.getParser(message.chatId).flatMap(parser -> parser.parse(message)).ifPresent(MessageSaver.INSTANCE::save);
                } catch (Exception e) {
                    var chatId = message.chatId;
                    String parserName = config.getParserName(chatId);
                    log.error("parser error, chatId: {}, : ", e);
                }

            } else if (object instanceof TdApi.UpdateAuthorizationState update) {
                log.info("授权状态更新：{}", update.authorizationState);
                if (update.authorizationState instanceof TdApi.AuthorizationStateWaitTdlibParameters) {
                    TdApi.SetTdlibParameters request = new TdApi.SetTdlibParameters();
                    request.databaseDirectory = "tdlib";
                    request.useMessageDatabase = true;
                    request.useSecretChats = true;
                    request.apiId = Integer.parseInt(System.getenv("TD_API_ID"));
                    request.apiHash = System.getenv("TD_API_HASH");
                    request.systemLanguageCode = "en";
                    request.deviceModel = "Desktop";
                    request.applicationVersion = "1.0";
                    client.send(request, result -> {
                        if (result instanceof TdApi.Ok) {
                            log.info("TDLib 参数设置成功");
                        }
                    });
                } else if (update.authorizationState instanceof TdApi.AuthorizationStateWaitPhoneNumber) {
                    log.info("请输入手机号: ");
                    String phoneNumber = scanner.nextLine();
                    client.send(new TdApi.SetAuthenticationPhoneNumber(phoneNumber, null), result -> {
                        if (result instanceof TdApi.Ok) {
                            log.info("已发送手机号，等待验证码...");
                        } else {
                            log.info("设置手机号失败：{}", result);
                        }
                    });
                } else if (update.authorizationState instanceof TdApi.AuthorizationStateWaitPassword) {
                    log.info("请输入密码（两步验证）：");
                    String password = scanner.nextLine();
                    client.send(new TdApi.CheckAuthenticationPassword(password), result -> {
                        if (result instanceof TdApi.Ok) {
                            log.info("密码正确，正在登录...");
                        } else {
                            log.error("密码验证失败：{}", result);
                        }
                    });
                } else if (update.authorizationState instanceof TdApi.AuthorizationStateWaitCode) {
                    log.info("请输入验证码: ");
                    String code = scanner.nextLine();
                    client.send(new TdApi.CheckAuthenticationCode(code), result -> {
                        if (result instanceof TdApi.Ok) {
                            log.info("验证码正确，正在登录...");
                        } else {
                            log.error("认证失败：{}", result);
                        }
                    });
                } else if (update.authorizationState instanceof TdApi.AuthorizationStateReady) {
                    log.info("登录成功！");
                    // 获取聊天列表
                    client.send(new TdApi.LoadChats(new TdApi.ChatListMain(), Integer.MAX_VALUE), loadResult -> {
                        if (loadResult instanceof TdApi.Ok) {
                            fetchChats();
                        } else {
                            log.error("加载聊天失败: {}", loadResult);
                        }
                    });
                }
            }
//            } else if (object instanceof TdApi.UpdateNewChat update) {
//                TdApi.Chat chat = update.chat;
//                if (config.containsChatId(chat.id)) {
//                    return;
//                }
//                log.info("新聊天: {} chat id: {}", chat.title, chat.id);
//                if (chat.type instanceof TdApi.ChatTypeSupergroup type) {
//                    if (!type.isChannel) {
//                        log.info("你加入了一个【群组】: {}, id: {}", chat.title, chat.id);
//                        config.addSuperGroup(chat.id, chat.title);
//                    } else {
//                        log.info("你订阅了一个【频道】: {}, id: {}", chat.title, chat.id);
//                        config.addNewsChannel(chat.id, chat.title);
//                    }
//                    getSupergroupBotMembers(chat.id, type.supergroupId, (botId, botName) -> {
//                        if (config.ignoreBot(chat.id)) {
//                            botConfig.addBotId(chat.id, botId);
//                            readableBotIdMap.computeIfAbsent(chat.title, k -> new ArrayList<>()).add(botName);
//                        }
//                    });
//                } else if (chat.type instanceof TdApi.ChatTypeBasicGroup) {
//                    log.info("你加入了一个【普通群组】: {}, id: {}", chat.title, chat.id);
//                } else if (chat.type instanceof TdApi.ChatTypePrivate) {
//                    log.info("私聊: {}", chat.title);
//                }
//            }

        }

        @Override
        public void onResult(TdApi.Object object) {
            try {
                handleMessage(object);
            } catch (Exception e) {
                log.error("处理消息时发生错误: {}", e.getMessage(), e);
            }
        }
    }

    public void fetchChats() {
        client.send(new TdApi.GetChats(new TdApi.ChatListMain(), Integer.MAX_VALUE), result -> {
            if (result instanceof TdApi.Chats chats) {
                for (long chatId : chats.chatIds) {
                    client.send(new TdApi.GetChat(chatId), chatResult -> {
                        if (chatResult instanceof TdApi.Chat chat) {
                            log.debug("{} ========> chat id: {} chat type: {}", chat.title, chat.id, chat.type);
                            if (chat.type instanceof TdApi.ChatTypeSupergroup supergroupType) {
                                long supergroupId = supergroupType.supergroupId;
                                if (supergroupType.isChannel) {
                                    config.addSuperGroup(supergroupId, chat.title);
                                } else {
                                    config.addNewsChannel(supergroupId, chat.title);
                                }
                                getSupergroupBotMembers(chatId, supergroupId, (botId, botName) -> {
                                    if (config.ignoreBot(chatId)) {
                                        botConfig.addBotId(chatId, botId);
                                        readableBotIdMap.computeIfAbsent(chat.title, k -> new ArrayList<>()).add(botName);
                                    }
                                });
                            } else if (chat.type instanceof TdApi.ChatTypeBasicGroup basicGroupType) {
                                // 获取普通群组成员，目前未监控普通群，只输出日志
                                getBasicGroupMembers(basicGroupType.basicGroupId);
                            }
                        } else {
                            log.error("获取聊天信息失败: {}", chatResult);
                        }
                    });
                }
            } else {
                log.error("获取聊天列表失败: {}", result);
            }
        });
    }

    private void getSupergroupBotMembers(long chatId, long supergroupId, BiConsumer<Long, String> consumer) {
        client.send(new TdApi.GetSupergroup(supergroupId), object -> {
            if (object instanceof TdApi.Supergroup supergroup) {
                TdApi.ChatMemberStatus status = supergroup.status;
                if (status instanceof TdApi.ChatMemberStatusMember ||
                        status instanceof TdApi.ChatMemberStatusAdministrator ||
                        status instanceof TdApi.ChatMemberStatusCreator || status instanceof TdApi.ChatMemberStatusRestricted) {
                    if (status instanceof TdApi.ChatMemberStatusRestricted restricted) {
                        if (!restricted.isMember) {
                            log.info("不在群里, chatId {}.", chatId);
                            return;
                        }
                    }
                    client.send(new TdApi.GetSupergroupMembers((int) supergroupId, new TdApi.SupergroupMembersFilterBots(), 0, Integer.MAX_VALUE), result -> {
                        if (result instanceof TdApi.ChatMembers members) {
                            for (TdApi.ChatMember member : members.members) {
                                if (member.memberId instanceof TdApi.MessageSenderUser senderUser) {
                                    long botId = senderUser.userId;
                                    getUserInfo(botId, botName -> consumer.accept(botId, botName));
                                }
                            }
                        }
                    });
                } else {
                    log.info("不在群里, chatId {}", chatId);
                }
            }
        });

    }

    private void getBasicGroupMembers(long basicGroupId) {
        client.send(new TdApi.GetBasicGroupFullInfo((int) basicGroupId), result -> {
            if (result instanceof TdApi.BasicGroupFullInfo fullInfo) {
                log.info("Basic Group Member Count: {}", fullInfo.members.length);
                for (TdApi.ChatMember member : fullInfo.members) {
                    log.info("Member ID: {}", member.memberId);
                }
            }
        });
    }

    private void getUserInfo(long userId, Consumer<String> consumer) {
        client.send(new TdApi.GetUser(userId), object -> {
            if (object instanceof TdApi.User user) {
                log.info("bot : {}", user);
                consumer.accept(user.firstName + user.lastName);
            } else {
                log.error("Failed to get user info.");
            }
        });
    }

    public void start() {
        setProxy(client).setLogLevels(2);
        Runnable task = () -> {
            fetchChats();
            log.info("BotIdMap: {}", readableBotIdMap);
            removeBotMessages();
        };
        scheduler.scheduleAtFixedRate(task, 20, 30, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Client.ExecutionException {
        TelegramReceiver receiver = new TelegramReceiver();
        receiver.start();
    }
}
