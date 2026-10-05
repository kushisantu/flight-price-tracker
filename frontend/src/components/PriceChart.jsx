import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { formatShort, money } from "../format";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

export default function PriceChart({ history, target, height = 240 }) {
  if (!history?.length) {
    return <p className="muted">Price history will show up after a route is selected.</p>;
  }
  const labels = history.map((point) => formatShort(point.date));
  const prices = history.map((point) => point.price);
  const average = Math.round(prices.reduce((sum, price) => sum + price, 0) / prices.length);
  const datasets = [
    {
      label: "Cheapest fare",
      data: prices,
      borderColor: "#1a73e8",
      backgroundColor: "rgba(26, 115, 232, 0.12)",
      fill: true,
      tension: 0.35,
      pointRadius: 0,
      pointHoverRadius: 4,
      borderWidth: 2,
    },
    {
      label: "Average",
      data: prices.map(() => average),
      borderColor: "#9aa3af",
      borderDash: [5, 4],
      pointRadius: 0,
      fill: false,
      borderWidth: 1.5,
    },
  ];
  if (target) {
    datasets.push({
      label: "Your target",
      data: prices.map(() => target),
      borderColor: "#0f7b3a",
      borderDash: [2, 3],
      pointRadius: 0,
      fill: false,
      borderWidth: 1.5,
    });
  }

  return (
    <div className="chart-wrap" style={{ height }}>
      <Line
        data={{ labels, datasets }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => `${item.dataset.label}: ${money(item.parsed.y)}`,
              },
            },
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { maxTicksLimit: 6, color: "#5c6775" },
            },
            y: {
              grid: { color: "#eef2f6" },
              ticks: {
                color: "#5c6775",
                callback: (value) => `$${value}`,
              },
            },
          },
        }}
      />
    </div>
  );
}
