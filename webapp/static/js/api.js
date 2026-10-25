// Talking to the server (webapp/server.py).

export async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} answered ${response.status}`);
  return response.json();
}
