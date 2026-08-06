% fft_week8.m - S5 W8 周日预习图: 傅里叶级数 -> 傅里叶变换
% 六格: (a)周期方波时域 (b)离散谱+Sa包络 (c)门函数时域
%       (d)连续谱 Sa (e)窄宽对比 (f)冲激串=包络取点
figure('visible','off','position',[60 60 1280 820]);

% ---- (a) 周期方波时域 ----
subplot(2,3,1);
t = linspace(-3*2*pi, 3*2*pi, 2000);
x = sign(sin(t));
plot(t, x, 'b', 'linewidth', 1.4); ylim([-1.6 1.6]);
grid on; title('(a) Periodic square wave  x(t)');
xlabel('t'); ylabel('x(t)');

% ---- (b) 周期方波离散谱 (梳子) + Sa 包络 ----
subplot(2,3,2);
n = -12:12; an = zeros(size(n));
nz = (n ~= 0);
an(nz) = 0.5*sin(n(nz)*pi/2)./(n(nz)*pi/2);
an(n == 0) = 0.5;
stem(n, abs(an), 'b', 'filled', 'markersize', 4); hold on;
w = linspace(-3*pi, 3*pi, 500);
env = 0.5*abs(sin(w*pi/2)./(w*pi/2)); env(abs(w) < 1e-9) = 0.5;
plot(w, env, 'r--', 'linewidth', 1.1);
xlim([-3*pi 3*pi]); grid on;
title('(b) Discrete spectrum (comb)');
xlabel('n\omega_0'); ylabel('|a_n|');
legend('lines', 'Sa envelope', 'location', 'northwest');

% ---- (c) 门函数时域 ----
subplot(2,3,3);
tau = 2;
t = linspace(-4, 4, 1200);
x = double(abs(t) <= tau/2);
plot(t, x, 'b', 'linewidth', 2); ylim([-0.3 1.4]);
grid on; title('(c) Gate pulse  \tau=2');
xlabel('t'); ylabel('x(t)');

% ---- (d) 门函数连续谱 (Sa) ----
subplot(2,3,4);
w = linspace(-3*pi, 3*pi, 800);
X = tau*sinc(w*tau/(2*pi));   % tau * sin(w*tau/2)/(w*tau/2)
plot(w, X, 'b', 'linewidth', 1.5); hold on;
plot([-3*pi 3*pi], [0 0], 'k', 'linewidth', 0.6);
grid on; title('(d) Continuous spectrum  \tau Sa(\omega\tau/2)');
xlabel('\omega'); ylabel('X(j\omega)');

% ---- (e) 窄宽对比: 时域窄 <-> 频域宽 ----
subplot(2,3,5);
w = linspace(-3*pi, 3*pi, 800);
X1 = 0.5*sinc(w*0.5/(2*pi));  % tau=0.5
X2 = 2*sinc(w*2/(2*pi));      % tau=2
plot(w, abs(X1), 'r', 'linewidth', 1.5); hold on;
plot(w, abs(X2), 'b', 'linewidth', 1.5);
grid on; title('(e) Narrow vs wide pulse');
xlabel('\omega'); ylabel('|X(j\omega)|');
legend('\tau=0.5 -> wide band', '\tau=2 -> narrow band', 'location', 'north');

% ---- (f) 周期信号频谱 = 冲激串 (包络取点) ----
subplot(2,3,6);
w2 = linspace(-3*pi, 3*pi, 500);
env2 = 0.5*abs(sin(w2*pi/2)./(w2*pi/2)); env2(abs(w2) < 1e-9) = 0.5;
stem(n, abs(an), 'b', 'filled', 'markersize', 4); hold on;
plot(w2, env2, 'r--', 'linewidth', 1.1);
xlim([-3*pi 3*pi]); grid on;
title('(f) Comb = samples on Sa envelope');
xlabel('n\omega_0'); ylabel('|a_n|');

print('-dpng', '-r150', '/workspace/blhx_scheduler/plots/fft_week8.png');
printf('saved ok\n');
