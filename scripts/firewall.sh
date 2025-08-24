# 先允许本地回环访问（lo接口）这个端口
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="127.0.0.1" port protocol="tcp" port="9178" accept'

# 拒绝其他所有来源访问这个端口
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" port protocol="tcp" port="9178" drop'

# IPv6 本地回环（如果你启用了 IPv6 PostgreSQL）
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv6" source address="::1" port protocol="tcp" port="9178" accept'
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv6" port protocol="tcp" port="9178" drop'

# 重新加载防火墙规则
sudo firewall-cmd --reload


# 允许指定外部 IPv4 地址访问 9178 端口
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="223.73.0.147" port protocol="tcp" port="9178" accept'
sudo firewall-cmd --reload

# 清除外部 IPv4 地址访问 9178 端口的规则
sudo firewall-cmd --permanent --remove-rich-rule='rule family="ipv4" source address="223.73.0.147" port protocol="tcp" port="9178" accept'
sudo firewall-cmd --reload