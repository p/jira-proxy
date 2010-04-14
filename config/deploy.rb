load 'deploy'

set :application, 'issues'

role :web, 'etal.bsdpower.com'

set :user, 'jiraproxy'
set :deploy_to, "/home/#{user}/#{application}"
set :cache_dir, "/var/cache/#{application}"

set :scm, :subversion
set :repository, "http://svn.bsdpower.com/webtools/jira-proxy/trunk"
set :deploy_via, :export

set :keep_releases, 5
# deploy:cleanup wants to use sudo
set :use_sudo, false

namespace :deploy do
  task :setup do
    run "mkdir -p #{releases_path} #{shared_path} #{shared_path}/config"
  end
  
  task :finalize_update do
    run <<-CMD
      for file in main.ini fastcgi.ini; do
        ln -s #{shared_path}/config/$file #{release_path}/config;
      done
    CMD
  end
  
  task :restart do
    sudo "fcgictl issues softrestart"
  end
  
  task :clear_proxy_cache do
    run "rm -rf #{cache_dir}/*"
  end
end
