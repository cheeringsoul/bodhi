package io.github.cheeringsoul;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import io.github.cheeringsoul.pojo.CrawledData;
import lombok.extern.slf4j.Slf4j;
import org.drinkless.tdlib.TdApi;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;

@Slf4j
public class Utils {
    public static List<String> extractLinks(String messageText) {
        if (messageText == null) {
            return Collections.emptyList();
        }

        List<String> links = new ArrayList<>();
        Matcher matcher = Pattern.compile("(https?://\\S+)").matcher(messageText);

        while (matcher.find()) {
            links.add(matcher.group());
        }
        return links;
    }

    public static CrawledData crawlUrl(String url) {
        try {
            Document doc = Jsoup.connect(url).get();
            String title = doc.title();
            String content = doc.body().text();
            return new CrawledData(url, title, content, doc);
        } catch (Exception e) {
            log.error("crawl error, url: {}, exception: {}", url, e.getMessage());
            return new CrawledData(url, null, null, null);
        }
    }

    public static void main(String[] args) {
        String url = "https://www.odaily.news/newsflash/438891";
        CrawledData crawledData = crawlUrl(url);
        var j = crawledData.doc().select("._4z3rUROM").text().trim();
        System.out.println("Title: " + crawledData.title());

        String html = "<div class=\"_4z3rUROM\"><p>Odaily星球日报讯&nbsp;消费级区块链项目 Abstract 在 X 平台发文询问“什么是 CA（on Abstract）”，疑似暗示发币。<br>此前 Pudgy Penguins 首席执行官 Luca Netz 在直播中暗示，Layer 2 网络 Abstract Chain 或将于年底前 TGE，当时他声称：“在年底前意味着 9 月、10 月、11 月、12 月”。</p></div>";

        Document doc = Jsoup.parse(html);
        Element div = doc.selectFirst("div._4z3rUROM");

    }

    // 获取发送者的 userId
    public static long getSenderUserId(TdApi.MessageSender sender) {
        return sender instanceof TdApi.MessageSenderUser ? ((TdApi.MessageSenderUser) sender).userId : -1;
    }
}
