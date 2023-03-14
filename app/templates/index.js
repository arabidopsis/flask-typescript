(function () {
    const form = document.getElementById('myform')
    const result = document.getElementById('result')

    form.addEventListener('submit', async (e) => {
        e.preventDefault()
        // e.stopPropagation()
        result.textContent = ''
        const formData = new FormData(form)
        for (const [key, value] of formData) {
            result.textContent += `${key}: ${value}\n`;
        }

        const resp = await fetch(form.action, { method: 'post', body: formData })
        const json = await resp.json()
        console.log(resp.ok, json)


    })



    const json1 = document.getElementById('json1')
    json1.addEventListener('click', async (e) => {
        const resp = await fetch('/json', { method: 'post' })
        const json = await resp.json()
        console.log(resp.ok, json, typeof json)
        //await getit(form.action, new FormData(form))
    })
})()
