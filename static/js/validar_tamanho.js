// Monitora a página inteira para qualquer mudança em inputs
document.addEventListener('change', function (event) {
    // Verifica se o elemento alterado é um campo de arquivo
    if (event.target && event.target.type === 'file') {
        const input = event.target;
        
        if (input.files && input.files[0]) {
            const arquivo = input.files[0];
            const tamanhoMaximo = 3 * 1024 * 1024; // 3 MB em Bytes (ajustado para o seu novo teste)
            
            if (arquivo.size > tamanhoMaximo) {
                // Alerta amigável
                alert(`O arquivo "${arquivo.name}" é muito grande!\nO limite máximo permitido é de 3 MB. O seu arquivo tem ${(arquivo.size / (1024 * 1024)).toFixed(2)} MB.`);
                
                // Trava o upload limpando o campo imediatamente
                input.value = '';
            }
        }
    }
});
